package metric;

import java.io.IOException;
import java.net.URI;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
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

	private static final int NUM_PARTS = 5000;
	private static final String SYNBIOHUB_BACKEND_URL = "https://dev.synbiohub.org";
	private static final String SYNBIOHUB_BACKEND_URL_NOEX = "https://synbiohub.org";
	private static final String SYNBIOHUB_URI_PREFIX = "https://synbiohub.org";

	private static final SynBioHubFrontend frontend = new SynBioHubFrontend(SYNBIOHUB_BACKEND_URL,
			SYNBIOHUB_URI_PREFIX);

	private static final SynBioHubFrontend frontend_noex = new SynBioHubFrontend(SYNBIOHUB_BACKEND_URL_NOEX,
			SYNBIOHUB_URI_PREFIX);

	public static void main(String[] args) throws Exception {
		List<ComponentDefinition> engineeredRegions = getEngineeredRegions();

		System.out.println("Getting metrics using SBOLExplorer");
		ArrayList<Double> sbolExplorerScores = getMetric(frontend, NUM_PARTS, engineeredRegions);
		System.out.println("Done getting metrics using SBOLExplorer");

		//System.in.read();

		System.out.println("Getting metrics without using SBOLExplorer");
		ArrayList<Double> noSBOLExplorerScores = getMetric(frontend_noex, NUM_PARTS, engineeredRegions);
		System.out.println("Done getting metrics without using SBOLExplorer");

		analyzeScores(sbolExplorerScores, noSBOLExplorerScores);
	}

	private static List<ComponentDefinition> getEngineeredRegions() throws IOException, Exception {
		HashSet<URI> collections = new HashSet<URI>();
		collections.add(URI.create("https://synbiohub.org/public/igem/igem_collection/1"));
		SynBioHubQuery query = new SynBioHubQuery(frontend_noex,
				new HashSet<URI>(Arrays.asList(SequenceOntology.ENGINEERED_REGION)), new HashSet<URI>(),
				collections, null, "ComponentDefinition");

		ArrayList<IdentifiedMetadata> metadatas = query.execute();
		ArrayList<ComponentDefinition> cds = new ArrayList<>();

		System.out.println(metadatas.size());
		for (IdentifiedMetadata metadata : metadatas) {
			System.out.println("Fetching: "+metadata.getUri() + " (" + cds.size() + ")");
			try {
				SBOLDocument doc = frontend.getSBOL(URI.create(metadata.getUri()),false);
				ComponentDefinition cd = doc.getRootComponentDefinitions().iterator().next();

				if (!cd.getComponents().isEmpty()) {
					cds.add(cd);

					if (cds.size() == NUM_PARTS) {
						break;
					}
				}
			} catch (SynBioHubException e) {
				System.out.println("URL:"+frontend.getBackendUrl());
				System.out.println("URI:"+metadata.getUri());
				e.printStackTrace();
			}
		}

		return cds;
	}

	private static ArrayList<Double> getMetric(SynBioHubFrontend frontend, 
			int numParts, List<ComponentDefinition> engineeredRegions)
			throws Exception {
//		ArrayList<Double> scores = new ArrayList<>();
		ArrayList<Double> indices = new ArrayList<>();
		int parts = 0;
		int total = 0;
		int found = 0;
		
		for (ComponentDefinition cd : engineeredRegions) {
			parts++;
			List<String> results = null;
			try {
				HashSet<URI> collections = new HashSet<URI>();
//				collections.add(URI.create("https://synbiohub.org/public/igem/igem_collection/1"));
				SynBioHubQuery query = new SynBioHubQuery(frontend, new HashSet<URI>(), new HashSet<URI>(),
						collections, cd.getDescription().replaceAll("&"," ").replace("'", "").trim(), "ComponentDefinition");
				results = Lists.transform(query.execute(), metadata -> metadata.getUri());
			} catch (Exception e) {
				System.out.println("Exception: skipping " + cd.getDisplayId());
				e.printStackTrace();
				continue;
			}
//			ArrayList<Double> indices = new ArrayList<>();

			for (Component child : cd.getComponents()) {
				int index = results.indexOf(child.getDefinitionURI().toString());
				total++;
				if (index >= 0) {
					found++;
					indices.add((double) index);
				} else {
					//indices.add(10000.0);
				}
			}
			//if (indices.size()>0) {
				//scores.add(average(indices));
			//}
			System.out.println(cd.getIdentity() + " (" + found + " out of " + total + ")");

			if (parts == numParts) {
				break;
			}
		}
		System.out.println("Total: "+found+" found out of "+total);
		return indices;
	}

	private static void analyzeScores(ArrayList<Double> sbolExplorerScores, ArrayList<Double> noSBOLExplorerScores) {
		assert (sbolExplorerScores.size() == noSBOLExplorerScores.size());

		System.out.println("Averages:");
		System.out.println("Using SBOLExplorer: " + average(sbolExplorerScores));
		System.out.println("Without using SBOLExplorer: " + average(noSBOLExplorerScores));

		System.out.println("Medians:");
		System.out.println("Using SBOLExplorer: " + median(sbolExplorerScores));
		System.out.println("Without using SBOLExplorer: " + median(noSBOLExplorerScores));
	}

	private static double average(ArrayList<Double> list) {
		return list.stream().mapToDouble(d -> d).average().orElse(0.0);
	}

	private static double median(ArrayList<Double> list) {
		Collections.sort(list);
		return list.get(list.size() / 2);
	}
}
