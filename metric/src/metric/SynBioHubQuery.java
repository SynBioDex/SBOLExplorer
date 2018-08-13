package metric;

import java.io.IOException;
import java.net.URI;
import java.util.ArrayList;
import java.util.Set;

import org.synbiohub.frontend.IdentifiedMetadata;
import org.synbiohub.frontend.SearchCriteria;
import org.synbiohub.frontend.SearchQuery;
import org.synbiohub.frontend.SynBioHubFrontend;

public class SynBioHubQuery {

	public static int QUERY_LIMIT = 10000;

	SynBioHubFrontend synBioHub;
	Set<URI> roles;
	Set<URI> types;
	Set<URI> collections;
	String filterText;
	String objectType;

	public SynBioHubQuery(SynBioHubFrontend synbiohub, Set<URI> roles, Set<URI> types, Set<URI> collections,
			String filterText, String objectType) throws IOException {
		this.synBioHub = synbiohub;
		this.roles = roles;
		this.types = types;
		this.collections = collections;
		this.filterText = filterText;
		this.objectType = objectType;
	}

	public ArrayList<IdentifiedMetadata> execute() throws Exception {
		// fetch parts
		SearchQuery query = new SearchQuery();
		query.setOffset(0);
		query.setLimit(QUERY_LIMIT);

		for (URI role : roles) {
			SearchCriteria criteria = new SearchCriteria();
			criteria.setKey("role");
			criteria.setValue(role.toString());
			query.addCriteria(criteria);
		}

		for (URI type : types) {
			SearchCriteria criteria = new SearchCriteria();
			criteria.setKey("type");
			criteria.setValue(type.toString());
			query.addCriteria(criteria);
		}

		for (URI collection : collections) {
			SearchCriteria criteria = new SearchCriteria();
			criteria.setKey("collection");
			criteria.setValue(collection.toString());
			query.addCriteria(criteria);
		}

		if (filterText != null && filterText != "") {
			SearchCriteria filterTextCriteria = new SearchCriteria();
			filterTextCriteria.setKey("name");
			filterTextCriteria.setValue(filterText);
			query.addCriteria(filterTextCriteria);
		}

		if (objectType != null && objectType != "") {
			SearchCriteria objectTypeCriteria = new SearchCriteria();
			objectTypeCriteria.setKey("objectType");
			objectTypeCriteria.setValue(objectType);
			query.addCriteria(objectTypeCriteria);
		}

		return synBioHub.search(query);
	}
}
