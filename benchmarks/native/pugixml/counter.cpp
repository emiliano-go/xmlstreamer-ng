// Raw parse-throughput reference: fully parse an XML feed with pugixml
// and count <item> elements. No Python semantics, speed only.
//
// Usage: pugixml_counter <file.xml> [rounds]
// Prints: <items>\t<best_seconds>

#include <cstdio>
#include <cstring>
#include <chrono>
#include <limits>

#include "pugixml.hpp"

static std::size_t count_items(pugi::xml_node node) {
    std::size_t n = 0;
    for (pugi::xml_node child : node.children()) {
        if (child.type() == pugi::node_element) {
            if (std::strcmp(child.name(), "item") == 0) {
                n += 1;
            } else {
                n += count_items(child);
            }
        }
    }
    return n;
}

int main(int argc, char** argv) {
    const char* path = argv[1];
    int rounds = argc > 2 ? std::atoi(argv[2]) : 1;
    double best = std::numeric_limits<double>::infinity();
    std::size_t items = 0;
    for (int i = 0; i < rounds; ++i) {
        auto t0 = std::chrono::steady_clock::now();
        pugi::xml_document doc;
        if (!doc.load_file(path, pugi::parse_default | pugi::parse_cdata)) {
            std::fprintf(stderr, "parse failed: %s\n", path);
            return 1;
        }
        items = count_items(doc.document_element());
        double secs = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - t0).count();
        if (secs < best) best = secs;
    }
    std::printf("%zu\t%.6f\n", items, best);
    return 0;
}
