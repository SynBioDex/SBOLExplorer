var svg = d3.select("svg"),
    width = +svg.attr("width"),
    height = +svg.attr("height");

var color = d3.scaleOrdinal(d3.schemeCategory20);

var limit = 500;

var strength = -((10 / Math.log10(limit)).toPrecision(3));
var simulation = d3.forceSimulation()
    .force("link", d3.forceLink().id(function(d) { return d.id; }))
    .force("charge", d3.forceManyBody().strength(strength))
    .force("center", d3.forceCenter(width / 2, height / 2));

var sparqlQuery = `
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX dc: <http://purl.org/dc/elements/1.1/>
PREFIX sbh: <http://wiki.synbiohub.org/wiki/Terms/synbiohub#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX sbol: <http://sbols.org/v2#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX purl: <http://purl.obolibrary.org/obo/>

select distinct ?pcd ?ie ?ccd
WHERE
{
?pcd a sbol:ComponentDefinition ;
sbol:component ?sc;
prov:wasDerivedFrom ?ie .

?sc sbol:definition ?ccd
}
LIMIT
` + " " + limit;

var requestUrl = "https://synbiohub.org/sparql?query=" + encodeURIComponent(sparqlQuery);

d3.json(requestUrl, function(error, graph) {
  if (error) {
    console.log(requestUrl);
    throw error;
  }

  document.getElementById("text").innerHTML = sparqlQuery;

  var nodes = createNodes(graph);
  var links = createLinks(graph);
  createRoot(nodes, links);

  console.log("nodes: " + JSON.stringify(nodes));
  console.log("links: " + JSON.stringify(links));

  var link = svg.append("g")
      .attr("class", "links")
    .selectAll("line")
    .data(links)
    .enter().append("line")
      .attr("stroke-width", function(d) { return Math.sqrt(d.value); });

  var node = svg.append("g")
      .attr("class", "nodes")
    .selectAll("circle")
    .data(nodes)
    .enter().append("circle")
      .attr("r", 5)
      .attr("fill", function(d) { return color(d.group); })
      .call(d3.drag()
          .on("start", dragstarted)
          .on("drag", dragged)
          .on("end", dragended));

  node.append("title")
      .text(function(d) { return d.id; });

  simulation
      .nodes(nodes)
      .on("tick", ticked);

  simulation.force("link")
      .links(links)
      .strength(function(d) { return d.value });

  function ticked() {
    link
        .attr("x1", function(d) { return d.source.x; })
        .attr("y1", function(d) { return d.source.y; })
        .attr("x2", function(d) { return d.target.x; })
        .attr("y2", function(d) { return d.target.y; });

    node
        .attr("cx", function(d) { return d.x; })
        .attr("cy", function(d) { return d.y; });
  }
});

function dragstarted(d) {
  if (!d3.event.active) simulation.alphaTarget(0.3).restart();
  d.fx = d.x;
  d.fy = d.y;
}

function dragged(d) {
  d.fx = d3.event.x;
  d.fy = d3.event.y;
}

function dragended(d) {
  if (!d3.event.active) simulation.alphaTarget(0);
  d.fx = null;
  d.fy = null;
}

// TODO why doesn't array.includes work?
function includes(nodes, node) {
  for (var i = 0; i < nodes.length; i++) {
    if (nodes[i].id == node.id) {
      return true;
    }
  }
  return false;
}

function createNodes(graph) {
  var nodes = [];
  var bindings = graph["results"]["bindings"];

  for (var i = 0; i < bindings.length; i++) {
    var pcdNode = {};
    pcdNode.id = bindings[i]["pcd"].value;
    pcdNode.group = 1;
    if (!includes(nodes, pcdNode)) {
      nodes.push(pcdNode);
    }

    var ccdNode = {};
    ccdNode.id = bindings[i]["ccd"].value;
    ccdNode.group = 1;
    if (!includes(nodes, ccdNode)) {
      nodes.push(ccdNode);
    }
  }

  return nodes;
}

function createLinks(graph) {
  var links = [];
  var bindings = graph["results"]["bindings"];

  for (var i = 0; i < bindings.length; i++) {
    var link = {};
    link.source = bindings[i]["pcd"].value;
    link.target = bindings[i]["ccd"].value;
    link.value = 1;
    links.push(link);
  }

  return links;
}

function createRoot(nodes, links) {
  var root = {};
  root.id = "root";
  root.group = 2;

  for (var i = 0; i < nodes.length; i++) {
    var link = {};
    link.source = "root";
    link.target = nodes[i].id;
    link.value = .01;
    links.push(link);
  }

  nodes.push(root);
}
