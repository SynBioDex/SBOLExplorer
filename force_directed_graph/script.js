function handleQueryForm() {
  var sparqlQuery = generateQuery();
  handleQuery(sparqlQuery);
}

function handleQueryText() {
  var sparqlQuery = document.getElementById("queryText").value;
  handleQuery(sparqlQuery);
}

function handleQuery(sparqlQuery) {
  document.getElementById("query").innerHTML = sparqlQuery;

  var svg = d3.select("svg");
  svg.selectAll("*").remove();

  var width = +svg.attr("width");
  var height = +svg.attr("height");

  var color = d3.scaleOrdinal(d3.schemeCategory20);

  var simulation = d3.forceSimulation()
      .force("link", d3.forceLink().id(function(d) { return d.id; }))
      .force("charge", d3.forceManyBody().strength(-10))
      .force("center", d3.forceCenter(width / 2, height / 2));

  var requestUrl = "https://synbiohub.org/sparql?query=" + encodeURIComponent(sparqlQuery);
  d3.json(requestUrl, function(error, graph) {
    if (error) {
      console.log(requestUrl);
      throw error;
    }

    var nodes = createNodes(graph);
    var links = createLinks(graph);
    createRoot(nodes, links);

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

    node.on("click", clicked)

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

  function clicked(d) {
    window.open(d.id);
  }
}

function generateQuery() {
  var type = document.getElementById("type").value;
  var role = document.getElementById("role").value;
  var displayId = document.getElementById("displayId").value;

  // TODO tie in constraints to submission
  var constraints = `
  sbol:type <http://www.biopax.org/release/biopax-level3.owl#DnaRegion> ;
  sbol:role <http://identifiers.org/so/SO:0000167>
  `;
  // TODO doesn't work when below is included
  // sbol:displayId <BBa_K1585999>

  var headers = `
  PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
  PREFIX dcterms: <http://purl.org/dc/terms/>
  PREFIX dc: <http://purl.org/dc/elements/1.1/>
  PREFIX sbh: <http://wiki.synbiohub.org/wiki/Terms/synbiohub#>
  PREFIX prov: <http://www.w3.org/ns/prov#>
  PREFIX sbol: <http://sbols.org/v2#>
  PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
  PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
  PREFIX purl: <http://purl.obolibrary.org/obo/>
  `;

  var query = `
  select distinct ?pcd ?ccd
  WHERE
  {
    ?pcd a sbol:ComponentDefinition .
    ?ccd a sbol:ComponentDefinition .

    {
      ?pcd sbol:component ?zero .
      ?zero sbol:definition ?ccd .
    }
    UNION
    {
      ?pcd sbol:component ?zero .
      ?zero sbol:definition ?one .
      ?one sbol:component ?two .
      ?two sbol:definition ?ccd .
    }
    UNION
    {
      ?pcd sbol:component ?zero .
      ?zero sbol:definition ?one .
      ?one sbol:component ?two .
      ?two sbol:definition ?three .
      ?three sbol:component ?four .
      ?four sbol:definition ?ccd .
    } .

    {
      ?pcd ` + constraints + `
    }
    UNION
    {
      ?ccd ` + constraints + `
    }
  }
  `;

  var limit = "LIMIT " + document.getElementById("limit").value;

  return headers + query + limit;
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
