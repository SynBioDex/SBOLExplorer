#include <cstdio>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <array>

using namespace std;

std::string exec(const char* cmd) {
  std::array<char, 128> buffer;
  std::string result;
  std::shared_ptr<FILE> pipe(popen(cmd, "r"), pclose);
  if (!pipe) throw std::runtime_error("popen() failed!");
  while (!feof(pipe.get())) {
    if (fgets(buffer.data(), 128, pipe.get()) != nullptr)
      result += buffer.data();
  }
  return result;
}

int main() {
  string output = exec("./../../blast/ncbi-blast-2.7.1+-src/c++/ReleaseMT/bin/blastn -db ../../blast/db/synbiohubdb/synbiohub.fsa -query ../../blast/db/synbiohubdb/queries/query.fsa");

  // extract significant alignments
  "\(Bits\)  Value\n\n((?'line'.{1,}\n)(\g'line')*)"

  // split by newline
  
  // extract uri and score
  "(\S+)\s*[1-9]*\s*(\S+)"

}
