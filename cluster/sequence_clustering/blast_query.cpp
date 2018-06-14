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


vector<string> filter_whitespace(vector<string> &strs) {
  vector<string> filtered;

  for (string s : strs) {
    if (s != "" && s != " ") {
      filtered.push_back(s);
    }
  }

  return filtered;
}


std::string exec(const char *cmd) {
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


void blast_query(map<string, float> &distances, string db_path, string query_path) {
  string cmd = "blastn -db " + db_path + " -query " + query_path;
  string blast_out = exec(cmd.c_str());

  // split blast_out
  vector<string> lines;
  split(blast_out, lines, '\n');

  // move to start of characteristics
  int line_idx = 0;
  string prefix = "Sequences producing significant alignments:";
  while (lines[line_idx].compare(0, prefix.size(), prefix)) {
    line_idx++;

    if (line_idx >= lines.size()) {
      return;
    }
  }
  line_idx += 2;

  // parse characteristics
  while (lines[line_idx].size() != 0) {
    // extract uri and score
    vector<string> characteristics;
    split(lines[line_idx], characteristics, ' ');
    characteristics = filter_whitespace(characteristics);

    string uri = characteristics[0];
    const char* score_str = characteristics[characteristics.size() - 2].c_str();
    try {
      float score = atof(score_str);
      distances.insert(make_pair(uri, score));
      /*
      cout << score << " from " << lines[line_idx] << endl;
      for (string characteristic : characteristics) {
        cout << characteristic << endl;
      }
      */
    } catch (invalid_argument e) {
      cout << blast_out << endl;
      cout << "tried to parse:" << score_str << ":end" << endl;
      exit(1);
    }

    line_idx++;
  }
}
