package metric;

import java.io.IOException;
import java.net.URI;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import org.sbolstandard.core2.Component;
import org.sbolstandard.core2.ComponentDefinition;
import org.sbolstandard.core2.SBOLDocument;
import org.sbolstandard.core2.SequenceOntology;
import org.synbiohub.frontend.IdentifiedMetadata;
import org.synbiohub.frontend.SynBioHubException;
import org.synbiohub.frontend.SynBioHubFrontend;

import com.google.common.collect.Lists;

public class MetricTest {

	private static final int NUM_PARTS = 200;
	private static final String SYNBIOHUB_BACKEND_URL = "http://localhost:7777";
	private static final String SYNBIOHUB_URI_PREFIX = "https://synbiohub.org";

	private static final SynBioHubFrontend frontend = new SynBioHubFrontend(SYNBIOHUB_BACKEND_URL,
			SYNBIOHUB_URI_PREFIX);

	public static void main(String[] args) throws Exception {
		List<ComponentDefinition> engineeredRegions = getEngineeredRegions();

		System.out.println("Getting metrics using SBOLExplorer");
		ArrayList<Double> sbolExplorerScores = getMetric(NUM_PARTS, engineeredRegions);
		System.out.println("Done getting metrics using SBOLExplorer");

		System.in.read();

		System.out.println("Getting metrics without using SBOLExplorer");
		ArrayList<Double> noSBOLExplorerScores = getMetric(NUM_PARTS, engineeredRegions);
		System.out.println("Done getting metrics without using SBOLExplorer");

		analyzeScores(sbolExplorerScores, noSBOLExplorerScores);
	}

	private static List<ComponentDefinition> getEngineeredRegions() throws IOException, Exception {
		SynBioHubQuery query = new SynBioHubQuery(frontend,
				new HashSet<URI>(Arrays.asList(SequenceOntology.ENGINEERED_REGION)), new HashSet<URI>(),
				new HashSet<URI>(), null, "ComponentDefinition");

		ArrayList<IdentifiedMetadata> metadatas = query.execute();
		ArrayList<ComponentDefinition> cds = new ArrayList<>();

		System.out.println(metadatas.size());
		for (IdentifiedMetadata metadata : metadatas) {
			try {
				SBOLDocument doc = frontend.getSBOL(URI.create(metadata.getUri()));
				ComponentDefinition cd = doc.getRootComponentDefinitions().iterator().next();

				if (!cd.getComponents().isEmpty()) {
					cds.add(cd);
					System.out.println("got: " + cds.size());

					if (cds.size() == NUM_PARTS) {
						break;
					}
				}
			} catch (SynBioHubException e) {
				e.printStackTrace();
			}
		}

		return cds;
	}

	private static ArrayList<Double> getMetric(int numParts, List<ComponentDefinition> engineeredRegions)
			throws Exception {
		ArrayList<Double> scores = new ArrayList<>();

		for (ComponentDefinition cd : engineeredRegions) {
			List<String> results = null;
			try {
				SynBioHubQuery query = new SynBioHubQuery(frontend, new HashSet<URI>(), new HashSet<URI>(),
						new HashSet<URI>(), cd.getDescription(), "ComponentDefinition");
				results = Lists.transform(query.execute(), metadata -> metadata.getUri());
			} catch (Exception e) {
				System.out.println("Exception: skipping " + cd.getDisplayId());
				continue;
			}

			ArrayList<Double> indices = new ArrayList<>();

			for (Component child : cd.getComponents()) {
				int index = results.indexOf(child.getDefinition().getIdentity().toString());

				if (index >= 0) {
					indices.add((double) index);
				} else {
					indices.add(10000.0);
				}
			}

			scores.add(average(indices));

			System.out.print('|');

			if (scores.size() == numParts) {
				break;
			}
		}

		return scores;
	}

	private static void analyzeScores(ArrayList<Double> sbolExplorerScores, ArrayList<Double> noSBOLExplorerScores) {
		assert (sbolExplorerScores.size() == noSBOLExplorerScores.size());

		System.out.println("Averages:");
		System.out.println("Using SBOLExplorer: " + average(sbolExplorerScores));
		System.out.println("Without using SBOLExplorer: " + average(noSBOLExplorerScores));
	}

	private static double average(ArrayList<Double> list) {
		return list.stream().mapToDouble(d -> d).average().orElse(0.0);
	}

}
