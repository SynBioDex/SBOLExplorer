#include <map>
#include "blast_query.cpp"

int main() {
  map<string, float> distances;
  blast_query(distances, "../../blast/db/synbiohubdb/synbiohub.fsa", "../../blast/db/synbiohubdb/queries/query.fsa");
  for (auto distance : distances) {
    cout << distance.first << " " << distance.second << endl;
  }
  return 0;
}
