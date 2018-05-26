#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <array>
#include <vector>

using namespace std;


size_t split(const std::string &txt, std::vector<std::string> &strs, char ch)
{
    size_t pos = txt.find( ch );
    size_t initialPos = 0;
    strs.clear();

    // Decompose statement
    while( pos != std::string::npos ) {
        strs.push_back( txt.substr( initialPos, pos - initialPos ) );
        initialPos = pos + 1;

        pos = txt.find( ch, initialPos );
    }

    // Add the last one
    strs.push_back( txt.substr( initialPos, std::min( pos, txt.size() ) - initialPos + 1 ) );

    return strs.size();
}


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
  string blast_out = exec("./../../blast/ncbi-blast-2.7.1+-src/c++/ReleaseMT/bin/blastn -db ../../blast/db/synbiohubdb/synbiohub.fsa -query ../../blast/db/synbiohubdb/queries/query.fsa");

  // extract significant alignments
  vector<string> lines;
  split(blast_out, lines, '\n');

  int line_idx = 0;
  string prefix = "Sequences producing significant alignments:";
  while (lines[line_idx].compare(0, prefix.size(), prefix)) {
    line_idx++;
  }
  line_idx += 2;

  while (lines[line_idx].size() != 0) {
    // extract uri and score
    vector<string> characteristics;
    split(lines[line_idx], characteristics, ' ');

    string uri = characteristics[0];
    float score = atof(characteristics[characteristics.size() - 1].c_str());

    cout << uri << " " << score << endl;

    line_idx++;
  }

  return 0;
}
