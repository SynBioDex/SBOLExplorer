#include <bits/stdc++.h>
#include <algorithm>
#include "disjoint_set.cpp"
#include "blast_query.cpp"

using namespace std;

const int NUM_WORKERS = 8;
const float DISTANCE_THRESHOLD = .005;

struct partition {
  int low;
  int high;
  string thread_id;
};

vector<string> uris;
map<string, int> uri_ids;
vector<string> seqs;

UF* uf;
pthread_mutex_t uf_mutex;


void read_file() {
  ifstream f("../../blast/db/synbiohubdb/synbiohub.fsa");

  if (f.is_open()) {
    string line;
    int index = 0;

    while (getline(f, line)) {
      string identifier;

      string uri = line.substr(1, line.size());
      uris.push_back(uri);
      uri_ids.insert(make_pair(uri, index));

      getline(f, line);
      seqs.push_back(line);

      index++;
    }

    f.close();
  } else {
    cout << "Unable to open file" << endl;
  }
}


void write_query_file(const string &uri, const string &seq, const string &path) {
  ofstream f(path);

  if (f.is_open()) {
    f << ">" << uri << endl;
    f << seq << endl;

    f.close();
  } else {
    cout << "Unable to open file" << endl;
  }

  //cout << "Wrote query file: " << path << endl;
}


void* spin(void *args) {
  struct partition *p = (struct partition*) args;

  for (int uri_idx = p->low; uri_idx < p->high; uri_idx++) {
    map<string, float> distances;

    string query_path = "../../blast/db/synbiohubdb/queries/query" + p->thread_id + ".fsa";
    write_query_file(uris[uri_idx], seqs[uri_idx], query_path);

    blast_query(distances, "../../blast/db/synbiohubdb/synbiohub.fsa", query_path);

    int merged = 0;

    // TODO test change locking structure to batch merges
    for (auto distance : distances) {

      if (distance.second < DISTANCE_THRESHOLD) {
        pthread_mutex_lock(&uf_mutex);
        uf->merge(uri_idx, uri_ids[distance.first]);
        //cout << p->thread_id << " unioned  " << first << " " << second << " distance: " << distance << endl;
        pthread_mutex_unlock(&uf_mutex);

        merged++;
      } else {
        //cout << p->thread_id << " no union " << first << " " << second << " distance: " << distance << endl;
      }
    }

    cout << uri_idx - p->low << "/" << p->high - p->low << " merged: " << merged << endl;
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
  // read file
  read_file();

  // set up UF
  uf = new UF(uris.size());

  // create partitions
  vector<struct partition*> partitions;
  int interval_size = (uris.size() / NUM_WORKERS) + 1;

  int uri_id = 0;

  for (int i = 0; i < NUM_WORKERS; i++) {
    struct partition* p = (struct partition*) malloc(sizeof(struct partition));

    p->low = uri_id;
    uri_id = min(uri_id + interval_size, static_cast<int>(uris.size()));
    p->high = uri_id;

    p->thread_id = i + '0';

    partitions.push_back(p);
  }

  // create threads
  pthread_t threads[NUM_WORKERS];

  for (int i = 0; i < NUM_WORKERS; i++) {
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

