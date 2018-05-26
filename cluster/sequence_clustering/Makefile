all:	cluster	blast_query_test

cluster:	cluster.cpp blast_query.cpp disjoint_set.cpp
	g++ -g -std=c++11 -pthread cluster.cpp -o cluster.out

blast_query_test:	blast_query_test.cpp blast_query.cpp
	g++ -std=c++11 blast_query_test.cpp -o blast_query_test.out

clean:
	rm *.out
