use std::collections::{HashMap, VecDeque};
use std::sync::{Arc, Mutex};

use pyo3::prelude::*;
use pyo3::types::{PyAny, PyBytes, PyDict, PyList};

use rypipe_core::{
    MemoryBudget, ParallelStreamOpts, ParallelStreamingBatchIterator, ParseDiagnostics, Pipeline,
    RecordStream as CoreRecordStream, StreamState,
};
use rypipe_python::{
    execution_plan_from_kwargs, py_err_from_rypipe, record_batch_to_pyarrow,
    record_batches_to_pyarrow_batches, record_batches_to_pyarrow_table,
};

mod parser;
mod scan;
mod splitter;
mod stream_parser;
mod tokenizer;
mod xml;

use parser::XmlParser;
use splitter::XmlSplitter;
use stream_parser::{StreamRecord, XmlStreamParser};

/// Reject separator tags the XML name rules cannot allow, at the entry
/// point, exactly like the Python `Tokenizer` does.
fn validate_separator_tag(separator_tag: &str) -> PyResult<()> {
    if !xml::is_xml_name(separator_tag.as_bytes()) {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "separator_tag {separator_tag:?} is not a name an XML tag can have"
        )));
    }
    Ok(())
}

/// Parse a memory string ("64MiB", "1GB") or an int into bytes.
fn memory_bytes(value: &Bound<'_, PyAny>) -> PyResult<usize> {
    if let Ok(bytes) = value.extract::<usize>() {
        return Ok(bytes.max(1));
    }
    let text: String = value.extract()?;
    let text = text.trim();
    let split = text
        .find(|c: char| !c.is_ascii_digit() && c != '.')
        .unwrap_or(text.len());
    let (num, unit) = text.split_at(split);
    let num: f64 = num
        .parse()
        .map_err(|_| pyo3::exceptions::PyValueError::new_err("invalid memory value"))?;
    let mult: f64 = match unit.trim().to_ascii_uppercase().as_str() {
        "" | "B" => 1.0,
        "KB" => 1_000.0,
        "MB" => 1_000_000.0,
        "GB" => 1_000_000_000.0,
        "KIB" => 1024.0,
        "MIB" => 1024.0 * 1024.0,
        "GIB" => 1024.0 * 1024.0 * 1024.0,
        other => {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "unknown memory unit: {other:?}"
            )))
        }
    };
    Ok(((num * mult) as usize).max(1))
}

/// Parse a whole item document into `(flat_dict_or_None, collisions)`.
#[pyfunction]
fn parse_document(
    py: Python<'_>,
    doc: &[u8],
) -> PyResult<(Option<Py<PyDict>>, Vec<(String, String, String)>)> {
    let result = xml::parse_document(doc);
    let parsed = match result.parsed {
        Some(tags) => {
            let dict = PyDict::new(py);
            for (key, value) in tags {
                dict.set_item(key, value)?;
            }
            Some(dict.into())
        }
        None => None,
    };
    Ok((parsed, result.collisions))
}

#[pyfunction]
fn attvalue_is_well_formed(value: &[u8]) -> bool {
    xml::attvalue_is_well_formed(value)
}

#[pyfunction]
fn start_tag_is_well_formed(tag: &[u8]) -> bool {
    xml::start_tag_is_well_formed(tag)
}

#[pyfunction]
fn end_tag_is_well_formed(tag: &[u8]) -> bool {
    xml::end_tag_is_well_formed(tag)
}

#[pyfunction]
fn is_xml_name(raw: &[u8]) -> bool {
    xml::is_xml_name(raw)
}

/// Collects diagnostics from the streaming parser for Python to log.
#[derive(Default)]
struct DiagSink {
    events: Mutex<Vec<(String, String)>>,
    counters: Mutex<HashMap<String, usize>>,
}

impl ParseDiagnostics for DiagSink {
    fn warning(&self, code: &str, message: &str) {
        self.events
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .push((code.to_string(), message.to_string()));
    }

    fn counter(&self, name: &str, delta: usize) {
        *self
            .counters
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .entry(name.to_string())
            .or_insert(0) += delta;
    }
}

/// Incremental item stream: the rypipe `RecordStream` driver over the
/// xmlstreamer scanner. `feed` pushes bytes; `next_item` returns
/// `(2, item)`, `(1, None)` for need-more, `(0, None)` for EOF.
#[pyclass]
struct RecordStream {
    inner: CoreRecordStream<XmlStreamParser>,
    diag: Arc<DiagSink>,
    queue: VecDeque<StreamRecord>,
}

#[pymethods]
impl RecordStream {
    #[new]
    #[pyo3(signature = (separator_tag, buffer_size, max_section_size, on_limit_text, deadline_secs=None))]
    fn new(
        separator_tag: &str,
        buffer_size: usize,
        max_section_size: i64,
        on_limit_text: bool,
        deadline_secs: Option<f64>,
    ) -> Self {
        RecordStream {
            inner: CoreRecordStream::new(XmlStreamParser::new(
                separator_tag,
                buffer_size,
                max_section_size,
                on_limit_text,
                deadline_secs,
            )),
            diag: Arc::new(DiagSink::default()),
            queue: VecDeque::new(),
        }
    }

    fn feed(&mut self, chunk: &[u8]) -> PyResult<()> {
        self.inner.feed(chunk).map_err(py_err_from_rypipe)
    }

    fn finish(&mut self) {
        self.inner.finish();
    }

    fn malformed_tags(&self) -> usize {
        self.inner.parser().malformed_tags()
    }

    /// Whether any warning is pending (cheap; avoids building a list per item).
    fn has_logs(&self) -> bool {
        !self
            .diag
            .events
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .is_empty()
    }

    /// Drain the warnings the scan produced since the last call.
    fn take_logs<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let list = PyList::empty(py);
        let events = std::mem::take(
            &mut *self.diag.events.lock().unwrap_or_else(|e| e.into_inner()),
        );
        for (code, message) in events {
            list.append((code, message))?;
        }
        Ok(list)
    }

    fn next_item<'py>(&mut self, py: Python<'py>) -> PyResult<(u8, Py<PyAny>)> {
        loop {
            if let Some(record) = self.queue.pop_front() {
                return Ok((2, record_to_py(py, record)?));
            }
            // The parser can finish on its own (time budget exhausted) while
            // the driver still has bytes to pull: end the iteration there.
            if self.inner.parser().state_eof() {
                return Ok((0, py.None()));
            }
            let mut out: Vec<StreamRecord> = Vec::new();
            let state = self
                .inner
                .parse(&mut |record| out.push(record), &*self.diag)
                .map_err(py_err_from_rypipe)?;
            self.queue.extend(out);
            let has_queued = !self.queue.is_empty();
            match state {
                StreamState::Eof if has_queued => continue,
                StreamState::Eof => return Ok((0, py.None())),
                StreamState::NeedMore if has_queued => continue,
                StreamState::NeedMore => return Ok((1, py.None())),
                StreamState::Rows => continue,
            }
        }
    }
}

fn record_to_py(py: Python<'_>, record: StreamRecord) -> PyResult<Py<PyAny>> {
    let parsed = match record.parsed {
        Some(tags) => {
            let dict = PyDict::new(py);
            for (key, value) in tags {
                dict.set_item(key, value)?;
            }
            Some(dict.unbind())
        }
        None => None,
    };
    let payload = (
        PyBytes::new(py, &record.content),
        parsed,
        record.replaced,
        record.collisions,
    );
    Ok(payload.into_pyobject(py)?.unbind().into_any())
}

#[pyfunction]
#[pyo3(signature = (path, separator_tag="item".to_string(), field_mapping=None, drop_fields=None,
    filter=None, field_types=None, dictionary_columns=None, schema=None, auto_dict=false,
    auto_dict_threshold=None, auto_dict_max_size=None, strict_types=false,
    max_split_chunks=None, min_chunk_bytes=None, observer=None, use_mmap=true, prefault=false, validate="strict"))]
#[allow(clippy::too_many_arguments)]
fn read_xml(
    py: Python<'_>,
    path: String,
    separator_tag: String,
    field_mapping: Option<HashMap<String, String>>,
    drop_fields: Option<Vec<String>>,
    filter: Option<Bound<'_, PyAny>>,
    field_types: Option<HashMap<String, String>>,
    dictionary_columns: Option<Vec<String>>,
    schema: Option<Vec<String>>,
    auto_dict: bool,
    auto_dict_threshold: Option<f64>,
    auto_dict_max_size: Option<usize>,
    strict_types: bool,
    max_split_chunks: Option<usize>,
    min_chunk_bytes: Option<usize>,
    observer: Option<Bound<'_, PyAny>>,
    use_mmap: bool,
    prefault: bool,
    validate: &str,
) -> PyResult<Py<PyAny>> {
    validate_separator_tag(&separator_tag)?;
    let keep = parser::keep_set(schema.as_ref(), field_mapping.as_ref());
    let strict = match validate {
        "strict" => true,
        "fast" => false,
        other => {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "validate must be 'strict' or 'fast', got {other:?}"
            )))
        }
    };
    let types = parser::field_kinds(field_types.clone());
    let plan = execution_plan_from_kwargs(
        field_mapping,
        drop_fields,
        filter.as_ref(),
        field_types,
        dictionary_columns,
        schema,
        auto_dict,
        auto_dict_threshold,
        auto_dict_max_size,
        strict_types,
        max_split_chunks,
        min_chunk_bytes,
        observer.as_ref(),
    )?;
    let batch = py
        .detach(|| {
            Pipeline::new(
                XmlSplitter::new(&separator_tag),
                XmlParser::new(&separator_tag, types, keep, strict),
            )
            .with_plan(plan)
            .read_path(&path, use_mmap, prefault)
        })
        .map_err(py_err_from_rypipe)?;
    record_batches_to_pyarrow_table(py, &[batch]).map(|table| table.unbind())
}

#[pyfunction]
#[pyo3(signature = (path, separator_tag="item".to_string(), chunks=4, field_mapping=None,
    drop_fields=None, filter=None, field_types=None, dictionary_columns=None, schema=None,
    auto_dict=false, auto_dict_threshold=None, auto_dict_max_size=None, strict_types=false,
    max_split_chunks=None, min_chunk_bytes=None, observer=None, use_mmap=true, prefault=false, validate="strict"))]
#[allow(clippy::too_many_arguments)]
fn read_xml_par(
    py: Python<'_>,
    path: String,
    separator_tag: String,
    chunks: usize,
    field_mapping: Option<HashMap<String, String>>,
    drop_fields: Option<Vec<String>>,
    filter: Option<Bound<'_, PyAny>>,
    field_types: Option<HashMap<String, String>>,
    dictionary_columns: Option<Vec<String>>,
    schema: Option<Vec<String>>,
    auto_dict: bool,
    auto_dict_threshold: Option<f64>,
    auto_dict_max_size: Option<usize>,
    strict_types: bool,
    max_split_chunks: Option<usize>,
    min_chunk_bytes: Option<usize>,
    observer: Option<Bound<'_, PyAny>>,
    use_mmap: bool,
    prefault: bool,
    validate: &str,
) -> PyResult<Py<PyAny>> {
    validate_separator_tag(&separator_tag)?;
    let keep = parser::keep_set(schema.as_ref(), field_mapping.as_ref());
    let strict = match validate {
        "strict" => true,
        "fast" => false,
        other => {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "validate must be 'strict' or 'fast', got {other:?}"
            )))
        }
    };
    let types = parser::field_kinds(field_types.clone());
    let plan = execution_plan_from_kwargs(
        field_mapping,
        drop_fields,
        filter.as_ref(),
        field_types,
        dictionary_columns,
        schema,
        auto_dict,
        auto_dict_threshold,
        auto_dict_max_size,
        strict_types,
        max_split_chunks,
        min_chunk_bytes,
        observer.as_ref(),
    )?;
    let batches = py
        .detach(|| {
            Pipeline::new(
                XmlSplitter::new(&separator_tag),
                XmlParser::new(&separator_tag, types, keep, strict),
            )
            .with_plan(plan)
            .read_path_par(&path, chunks, use_mmap, prefault)
        })
        .map_err(py_err_from_rypipe)?;
    record_batches_to_pyarrow_table(py, &batches).map(|table| table.unbind())
}

/// Bounded-memory read: returns a list of `pyarrow.RecordBatch`.
#[pyfunction]
#[pyo3(signature = (path, separator_tag="item".to_string(), memory=None, field_mapping=None,
    drop_fields=None, filter=None, field_types=None, dictionary_columns=None, schema=None,
    auto_dict=false, auto_dict_threshold=None, auto_dict_max_size=None, strict_types=false,
    max_split_chunks=None, min_chunk_bytes=None, observer=None, use_mmap=true, prefault=false, validate="strict"))]
#[allow(clippy::too_many_arguments)]
fn read_xml_stream(
    py: Python<'_>,
    path: String,
    separator_tag: String,
    memory: Option<Bound<'_, PyAny>>,
    field_mapping: Option<HashMap<String, String>>,
    drop_fields: Option<Vec<String>>,
    filter: Option<Bound<'_, PyAny>>,
    field_types: Option<HashMap<String, String>>,
    dictionary_columns: Option<Vec<String>>,
    schema: Option<Vec<String>>,
    auto_dict: bool,
    auto_dict_threshold: Option<f64>,
    auto_dict_max_size: Option<usize>,
    strict_types: bool,
    max_split_chunks: Option<usize>,
    min_chunk_bytes: Option<usize>,
    observer: Option<Bound<'_, PyAny>>,
    use_mmap: bool,
    prefault: bool,
    validate: &str,
) -> PyResult<Py<PyAny>> {
    let _ = use_mmap; // the bounded path reads through InputBuffer directly
    let budget = match memory {
        Some(value) => MemoryBudget::new(memory_bytes(&value)?),
        None => MemoryBudget::new(64 * 1024 * 1024),
    };
    validate_separator_tag(&separator_tag)?;
    let keep = parser::keep_set(schema.as_ref(), field_mapping.as_ref());
    let strict = match validate {
        "strict" => true,
        "fast" => false,
        other => {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "validate must be 'strict' or 'fast', got {other:?}"
            )))
        }
    };
    let types = parser::field_kinds(field_types.clone());
    let plan = execution_plan_from_kwargs(
        field_mapping,
        drop_fields,
        filter.as_ref(),
        field_types,
        dictionary_columns,
        schema,
        auto_dict,
        auto_dict_threshold,
        auto_dict_max_size,
        strict_types,
        max_split_chunks,
        min_chunk_bytes,
        observer.as_ref(),
    )?;
    let batches = py
        .detach(|| {
            Pipeline::new(
                XmlSplitter::new(&separator_tag),
                XmlParser::new(&separator_tag, types, keep, strict),
            )
            .with_plan(plan)
            .read_path_stream(&path, budget, prefault)
        })
        .map_err(py_err_from_rypipe)?;
    record_batches_to_pyarrow_batches(py, &batches).map(|list| list.unbind().into_any())
}

/// Lazy iterator over `pyarrow.RecordBatch` from the parallel streaming engine.
///
/// The inner iterator lives behind a `Mutex` because its worker channel is
/// `Send` but not `Sync`, and pyclasses must be both.
#[pyclass]
struct ParallelBatches {
    inner: Arc<std::sync::Mutex<ParallelStreamingBatchIterator>>,
}

#[pymethods]
impl ParallelBatches {
    fn __iter__(slf: PyRef<'_, Self>) -> PyRef<'_, Self> {
        slf
    }

    fn __next__(&self, py: Python<'_>) -> PyResult<Option<Py<PyAny>>> {
        // The worker parses on other threads; release the GIL while waiting.
        let inner = Arc::clone(&self.inner);
        let next = py.detach(move || {
            inner
                .lock()
                .unwrap_or_else(|e| e.into_inner())
                .next()
        });
        match next {
            None => Ok(None),
            Some(Ok(batch)) => {
                Ok(Some(record_batch_to_pyarrow(py, &batch)?.unbind()))
            }
            Some(Err(err)) => Err(py_err_from_rypipe(err)),
        }
    }
}

/// Parallel streaming read: yields batches as the workers produce them,
/// in file order when `ordered` is true.
#[pyfunction]
#[pyo3(signature = (path, separator_tag="item".to_string(), threads=8, memory=None,
    ordered=true, field_mapping=None, drop_fields=None, filter=None, field_types=None,
    dictionary_columns=None, schema=None, auto_dict=false, auto_dict_threshold=None,
    auto_dict_max_size=None, strict_types=false, max_split_chunks=None, min_chunk_bytes=None, observer=None,
    use_mmap=true, prefault=false, validate="strict"))]
#[allow(clippy::too_many_arguments)]
fn iter_xml_batches_par(
    path: String,
    separator_tag: String,
    threads: usize,
    memory: Option<Bound<'_, PyAny>>,
    ordered: bool,
    field_mapping: Option<HashMap<String, String>>,
    drop_fields: Option<Vec<String>>,
    filter: Option<Bound<'_, PyAny>>,
    field_types: Option<HashMap<String, String>>,
    dictionary_columns: Option<Vec<String>>,
    schema: Option<Vec<String>>,
    auto_dict: bool,
    auto_dict_threshold: Option<f64>,
    auto_dict_max_size: Option<usize>,
    strict_types: bool,
    max_split_chunks: Option<usize>,
    min_chunk_bytes: Option<usize>,
    observer: Option<Bound<'_, PyAny>>,
    use_mmap: bool,
    prefault: bool,
    validate: &str,
) -> PyResult<ParallelBatches> {
    let _ = use_mmap; // parallel streaming always maps/decompresses via InputBuffer
    let budget = match memory {
        Some(value) => MemoryBudget::new(memory_bytes(&value)?),
        None => MemoryBudget::new(64 * 1024 * 1024),
    };
    validate_separator_tag(&separator_tag)?;
    let keep = parser::keep_set(schema.as_ref(), field_mapping.as_ref());
    let strict = match validate {
        "strict" => true,
        "fast" => false,
        other => {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "validate must be 'strict' or 'fast', got {other:?}"
            )))
        }
    };
    let types = parser::field_kinds(field_types.clone());
    let plan = execution_plan_from_kwargs(
        field_mapping,
        drop_fields,
        filter.as_ref(),
        field_types,
        dictionary_columns,
        schema,
        auto_dict,
        auto_dict_threshold,
        auto_dict_max_size,
        strict_types,
        max_split_chunks,
        min_chunk_bytes,
        observer.as_ref(),
    )?;
    let opts = ParallelStreamOpts {
        threads: threads.max(1),
        ordered,
        max_reorder: 0,
        schema: None,
    };
    let inner = ParallelStreamingBatchIterator::new(
        std::path::PathBuf::from(&path),
        XmlSplitter::new(&separator_tag),
        XmlParser::new(&separator_tag, types, keep, strict),
        Arc::new(plan),
        budget,
        prefault,
        opts,
    );
    Ok(ParallelBatches {
        inner: Arc::new(std::sync::Mutex::new(inner)),
    })
}

#[pymodule]
fn _xmlstreamer(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(parse_document, m)?)?;
    m.add_function(wrap_pyfunction!(attvalue_is_well_formed, m)?)?;
    m.add_function(wrap_pyfunction!(start_tag_is_well_formed, m)?)?;
    m.add_function(wrap_pyfunction!(end_tag_is_well_formed, m)?)?;
    m.add_function(wrap_pyfunction!(is_xml_name, m)?)?;
    m.add_function(wrap_pyfunction!(read_xml, m)?)?;
    m.add_function(wrap_pyfunction!(read_xml_par, m)?)?;
    m.add_function(wrap_pyfunction!(read_xml_stream, m)?)?;
    m.add_function(wrap_pyfunction!(iter_xml_batches_par, m)?)?;
    m.add_class::<ParallelBatches>()?;
    m.add_class::<RecordStream>()?;
    Ok(())
}
