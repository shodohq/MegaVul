#include <cstdlib>                                                                                                                                                                    
extern "C" {
void *tree_sitter_cpp_external_scanner_create() { return nullptr; }                                                                                                                   
void tree_sitter_cpp_external_scanner_destroy(void *) {}  
void tree_sitter_cpp_external_scanner_reset(void *, void *) {}
unsigned tree_sitter_cpp_external_scanner_serialize(void *, char *) { return 0; }
void tree_sitter_cpp_external_scanner_deserialize(void *, const char *, unsigned) {}
bool tree_sitter_cpp_external_scanner_scan(void *, void *, const bool *) { return false; }
}