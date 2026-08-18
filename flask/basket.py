from collections import defaultdict, Counter
from itertools import combinations
import query
from logger import Logger

logger_ = Logger()

DEFAULT_MIN_COUNT = 10
DEFAULT_TOP_K = 20


def _pages_to_baskets(pages):
    """
    Converts paged query_device_components() results into device_baskets and part_rols.

    Args:
        pages: Iterable of pages (from query_device_components())

    Returns: (device_baskets, part_roles)
        device_baskets -- {device_uri: frozenset(part_uri)}, devices with < 2 parts excluded
        part_roles -- {part_uri: role_uri} for parts seen as sub-components
    """
    device_baskets = defaultdict(set)
    part_roles = {}
    for page in pages:
        for row in page:
            parent = row['parent']
            child = row['childDef']
            device_baskets[parent].add(child)
            role = row.get('childRole')
            if role and 'identifiers.org' in role:
                part_roles[child] = role
    return device_baskets, part_roles


def fetch_device_basket(subject):
    """
    Queries Virtuoso for one device's current sub-part composition.

    Args:
        subject: Device URI

    Returns: (frozenset of part URIs, part_roles) if subject has >= 2 sub-parts, else (None, {})
    """
    device_baskets, part_roles = _pages_to_baskets(
        query.query_device_components(f'FILTER (?parent = <{subject}>)')
    )
    basket = device_baskets.get(subject, set())
    if len(basket) < 2:
        return None, {}
    return frozenset(basket), part_roles


def update_baskets():
    """
    Full rebuild: queries all device compositions. No rule table is built or
    stored -- recommendations are computed live from device_baskets at
    request time (see recommend() below), so this only needs to refresh the
    raw composition data.

    Returns: (device_baskets, part_roles)
        device_baskets -- {device_uri: frozenset(part_uri)}, devices with < 2 parts excluded
        part_roles -- {part_uri: role_uri} for parts seen as sub-components
    """
    logger_.log('------------ Updating baskets ------------', True)
    logger_.log('******** Query for device compositions ********', True)

    device_baskets, part_roles = _pages_to_baskets(query.query_device_components())
    device_baskets = {k: frozenset(v) for k, v in device_baskets.items() if len(v) >= 2}

    logger_.log(f'******** Query for device compositions complete: {len(device_baskets)} devices ********', True)
    logger_.log('------------ Successfully updated baskets ------------\n', True)

    return device_baskets, part_roles


def _item_counts(device_baskets):
    counts = Counter()
    for basket in device_baskets.values():
        for item in basket:
            counts[item] += 1
    return counts


def recommend(device_baskets, cart, min_count=DEFAULT_MIN_COUNT, top_k=DEFAULT_TOP_K):
    """
    Apriori-style recommendation for an arbitrary cart of selected parts.

    Args:
        device_baskets: {device_uri: frozenset(part_uri)}
        cart: Iterable of part URIs selected
        min_count: Minimum number of devices a (sub)set must appear in before
            its statistics are trusted
        top_k: Max number of recommendations to return

    Returns: (recommendations, matched_size)
        recommendations -- [(related_uri, confidence, lift, count), ...] sorted by lift desc
        matched_size -- size of the cart subset(s) that actually cleared min_count
            (equal to len(cart) if the full cart had enough support, smaller if backoff was needed,
            0 if nothing did)
    """
    cart = frozenset(cart)
    logger_.log(f'recommend(cart={sorted(cart)}, min_count={min_count}, top_k={top_k})')
    n = len(device_baskets)
    if n == 0 or not cart:
        return [], 0

    baskets = list(device_baskets.values())
    item_counts = _item_counts(device_baskets)

    for size in range(len(cart), 0, -1):
        candidate_scores = {}
        matched = False
        for subset in combinations(sorted(cart), size):
            subset = frozenset(subset)
            support = 0
            co_counts = Counter()
            for basket in baskets:
                if subset <= basket:
                    support += 1
                    for item in basket - cart:
                        co_counts[item] += 1
            if support == 0:
                continue
            for item, count in co_counts.items():
                if count < min_count:
                    continue
                matched = True
                confidence = count / support
                lift = count / n / ((support / n) * (item_counts[item] / n))
                if item not in candidate_scores or lift > candidate_scores[item][1]:
                    candidate_scores[item] = (confidence, lift, count)
        if matched:
            ranked = sorted(candidate_scores.items(), key=lambda kv: -kv[1][1])
            if top_k is not None:
                ranked = ranked[:top_k]
            recommendations = [(item, conf, lift, count) for item, (conf, lift, count) in ranked]
            return recommendations, size

    return [], 0


def refresh_device_baskets(device_baskets, part_roles, subjects):
    """
    Incrementally updates device_baskets/part_roles in place for a batch of
    touched subjects: re-queries each subject's current sub-part composition
    and overwrites (or removes) its entry.

    Args:
        device_baskets: Existing {device_uri: frozenset(part_uri)} to update in place
        part_roles: Existing {part_uri: role_uri} to update in place
        subjects: Iterable of subject URIs that were added/updated

    Returns: (device_baskets, part_roles) -- same dicts, mutated
    """
    for subject in subjects:
        basket, roles = fetch_device_basket(subject)
        if basket is not None:
            device_baskets[subject] = basket
            part_roles.update(roles)
        else:
            device_baskets.pop(subject, None)
    return device_baskets, part_roles


def remove_device_basket(device_baskets, subject):
    """
    Removes a subject's basket entry (incremental delete).

    Args:
        device_baskets: Existing {device_uri: frozenset(part_uri)}
        subject: Device URI to remove

    Returns: device_baskets (same dict, mutated)
    """
    device_baskets.pop(subject, None)
    return device_baskets
