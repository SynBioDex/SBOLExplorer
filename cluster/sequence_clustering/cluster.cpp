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
vector<string> seqs;

UF* uf;
pthread_mutex_t uf_mutex;


void read_file() {
  ifstream f("sequences.fsa");

  if (f.is_open()) {
    string line;
    int index = 0;

    while (getline(f, line)) {
      string identifier;

      uris.push_back(line.substr(1, strlen(line)));

      getline(f, line);
      seqs.push_back(line);
    }

    f.close();
  } else {
    cout << "Unable to open file" << endl;
  }
}


void* spin(void *args) {
  struct partition *p = (struct partition*) args;

  int i = 0;

  for (int first = p->first_partition.first; first < p->first_partition.second; first++) {
    for (int second = p->second_partition.first; second < p->second_partition.second; second++) {
      // TODO switch to blast
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
  // read file
  read_file();

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

