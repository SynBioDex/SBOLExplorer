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

import com.google.common.base.Function;
import com.google.common.collect.Lists;

public class MetricTest {

	private static final int NUM_PARTS = 80;
	private static final String SYNBIOHUB_BACKEND_URL = "http://localhost:7777";
	private static final String GET_SBOL_SYNBIOHUB_BACKEND_URL = "https://synbiohub.org";

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
		SynBioHubQuery query = new SynBioHubQuery(new SynBioHubFrontend(SYNBIOHUB_BACKEND_URL),
				new HashSet<URI>(Arrays.asList(SequenceOntology.ENGINEERED_REGION)), new HashSet<URI>(),
				new HashSet<URI>(), null, "ComponentDefinition");

		SynBioHubFrontend getSBOLFrontend = new SynBioHubFrontend(GET_SBOL_SYNBIOHUB_BACKEND_URL);

		Function<IdentifiedMetadata, ComponentDefinition> metadataToCD = new Function<IdentifiedMetadata, ComponentDefinition>() {
			public ComponentDefinition apply(IdentifiedMetadata metadata) {
				SBOLDocument doc;
				try {
					doc = getSBOLFrontend.getSBOL(URI.create(metadata.getUri()));
					return doc.getRootComponentDefinitions().iterator().next();
				} catch (SynBioHubException e) {
					e.printStackTrace();
					return null;
				}
			}
		};

		return Lists.transform(query.execute(), metadataToCD);
	}

	private static ArrayList<Double> getMetric(int numParts, List<ComponentDefinition> engineeredRegions)
			throws IOException, Exception {
		SynBioHubFrontend frontend = new SynBioHubFrontend(SYNBIOHUB_BACKEND_URL);

		ArrayList<Double> scores = new ArrayList<>();

		for (int i = 0; i < numParts; i++) {
			ComponentDefinition seed = engineeredRegions.get(i);

			SynBioHubQuery query = new SynBioHubQuery(frontend, new HashSet<URI>(), new HashSet<URI>(),
					new HashSet<URI>(), seed.getDescription(), "ComponentDefinition");
			List<String> results = Lists.transform(query.execute(), metadata -> metadata.getUri());

			ArrayList<Double> indices = new ArrayList<>();

			for (Component child : seed.getComponents()) {
				int index = results.indexOf(child.getDefinition().getIdentity().toString());

				if (index >= 0) {
					indices.add((double) index);
				} else {
					indices.add(10000.0);
				}
			}

			if (indices.isEmpty()) {
				System.out.println("No children");
			} else {
				double score = average(indices);
				System.out.println(score);
				scores.add(score);
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
