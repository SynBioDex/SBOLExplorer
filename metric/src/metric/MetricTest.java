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
import org.synbiohub.frontend.SynBioHubFrontend;

import com.google.common.collect.Lists;

public class MetricTest {

	public static void main(String[] args) throws Exception {
		SynBioHubFrontend frontend = new SynBioHubFrontend("http://localhost:7777");

		SynBioHubQuery query = new SynBioHubQuery(frontend,
				new HashSet<URI>(Arrays.asList(SequenceOntology.ENGINEERED_REGION)), new HashSet<URI>(),
				new HashSet<URI>(), null, "ComponentDefinition");
		ArrayList<IdentifiedMetadata> engineeredRegions = query.execute();

		for (int i = 0; i < 10; i++) {
			SBOLDocument doc = new SynBioHubFrontend("https://synbiohub.org")
					.getSBOL(URI.create(engineeredRegions.get(i).getUri()));
			ComponentDefinition seed = doc.getRootComponentDefinitions().iterator().next();

			query = new SynBioHubQuery(frontend, new HashSet<URI>(), new HashSet<URI>(), new HashSet<URI>(),
					seed.getDescription(), "ComponentDefinition");
			List<String> results = Lists.transform(query.execute(), x -> x.getUri());

			int numOfChildren = 0;
			int total = 0;

			for (Component child : seed.getComponents()) {
				int index = results.indexOf(child.getDefinition().getIdentity().toString());

				if (index >= 0) {
					total += index;
				} else {
					total += 10000;
				}

				numOfChildren++;
			}

			if (numOfChildren == 0) {
				System.out.println("No children");
			} else {
				System.out.println((double) total / numOfChildren);
			}
		}
	}

}
