#include <bits/stdc++.h>
#include "disjoint_set.cpp"

using namespace std;

const int NUM_WORKERS = 9;
const int NUM_RANGES = 3;
const float DISTANCE_THRESHOLD = .003125;

struct partition {
  pair<int, int> first_partition;
  pair<int, int> second_partition;
  int thread_id;
};

vector<string> uris;
vector<set<string>> grams;

UF* uf;
pthread_mutex_t uf_mutex;


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


void read_file() {
  ifstream f("grams.txt");

  if (f.is_open()) {
    string line;
    int index = 0;

    while (getline(f, line)) {
      vector<string> line_vector;
      split(line, line_vector, ' ');

      uris.push_back(line_vector[0]);

      grams.push_back({});
      for (int i = 1; i < line_vector.size(); i++) {
        grams[index].insert(line_vector[i]);
      }

      index++;
    }

    f.close();
  } else {
    cout << "Unable to open file" << endl;
  }

}


void print_grams() {
  for (const auto& uri: uris) {
    cout << uri << endl;
  }

  for (int s = 0; s < grams.size(); s++) {
    for (const string& g: grams[s]) {
      cout << g << " ";
    }
    cout << endl;
  }
}


float JD(int first, int second) {
  int intersection = 0;
  int _union = grams[first].size();

  for (const auto& gram: grams[second]) {
    if (grams[first].find(gram) != grams[first].end()) {
      intersection++;
    } else {
      _union++;
    }
  }

  if (_union == 0) {
    return 1.0;
  }

  return 1 - (((float) intersection) / _union);
}


void* spin(void *args) {
  struct partition *p = (struct partition*) args;

  int i = 0;

  for (int first = p->first_partition.first; first < p->first_partition.second; first++) {
    for (int second = p->second_partition.first; second < p->second_partition.second; second++) {
      float distance = JD(first, second);

      if (distance < DISTANCE_THRESHOLD) {
        pthread_mutex_lock(&uf_mutex);
        uf->merge(first, second);
        //cout << p->thread_id << " unioned  " << first << " " << second << " distance: " << distance << endl;
        pthread_mutex_unlock(&uf_mutex);
      } else {
        //cout << p->thread_id << " no union " << first << " " << second << " distance: " << distance << endl;
      }

      i++;
      if (i % 10000 == 0) {
        cout << p->thread_id << " iteration " << i << endl;
      }
    }
  }
}


void write_clusters() {
  ofstream f("clusters.txt");

  if (f.is_open()) {
    for (int i = 0; i < uris.size(); i++) {
      f << i << " " << uf->find(i) << endl;
    }

    f.close();
  } else {
    cout << "Unable to open file" << endl;
  }

  cout << "parts: " << uris.size() << endl;
  cout << "clusters: " << uf->count() << endl;
}


int main() {
  //ios::sync_with_stdio(false);

  // read file
  read_file();

  // print file
  print_grams();

  // set up UF
  uf = new UF(uris.size());

  // create partitions
  vector<struct partition*> partitions;
  int interval_size = uris.size() / NUM_RANGES;

  for (int first = 0; first < NUM_RANGES; first++) {
    for (int second = 0; second < NUM_RANGES; second++) {
      struct partition* p = (struct partition*) malloc(sizeof(struct partition));

      p->first_partition = make_pair(first * interval_size, (first+1) * interval_size);
      p->second_partition = make_pair(second * interval_size, (second+1) * interval_size);

      partitions.push_back(p);
    }
  }

  // create threads
  pthread_t threads[NUM_WORKERS];

  for (int i = 0; i < NUM_WORKERS; i++) {
    partitions[i]->thread_id = i;
    int ret = pthread_create(&threads[i], NULL, spin, partitions[i]);

    if (ret != 0) {
      printf("creating thread failed\n");
      return 1;
    }

    cout << "created thread: " << i << endl;
  }

  for (int i = 0; i < NUM_WORKERS; i++) {
    pthread_join(threads[i], NULL);
    cout << "joined thread: " << i << endl;
  }

  // write clusters
  write_clusters();
}

