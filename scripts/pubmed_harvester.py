from Bio import Entrez, Medline
from io import StringIO
import csv
import time
from datetime import datetime
from pathlib import Path

from config.local_config import ENTREZ_EMAIL

# Set the email required by the PubMed API
Entrez.email = ENTREZ_EMAIL


def read_queries(input_file="queries/pubmed_queries.txt"):
    """
    Read search queries from a text file.
    Empty lines are ignored.
    """
    with open(input_file, "r", encoding="utf-8") as file:
        queries = [line.strip() for line in file if line.strip()]
    return queries


def fetch_articles(id_list):
    """
    Fetch MEDLINE records for a list of PubMed IDs.
    """
    if not id_list:
        return ""

    ids = ",".join(id_list)

    handle = Entrez.efetch(
        db="pubmed",
        id=ids,
        rettype="medline",
        retmode="text"
    )

    articles = handle.read()
    handle.close()

    return articles


def parse_articles(text):
    """
    Parse MEDLINE text and extract useful metadata.
    """
    records = Medline.parse(StringIO(text))
    results = []

    for record in records:
        results.append({
            "PMID": record.get("PMID", ""),
            "Title": record.get("TI", ""),
            "Authors": "; ".join(record.get("AU", [])),
            "Journal": record.get("JT", ""),
            "Date": record.get("DP", ""),
            "Abstract": record.get("AB", "")
        })

    return results


def fetch_references_and_citations(pmid_list):
    """
    For each PMID, fetch:
    - references cited by the article
    - articles citing the article
    """
    results = {}

    for pmid in pmid_list:
        results[pmid] = {
            "References": [],
            "Citations": []
        }

        try:
            handle_refs = Entrez.elink(
                dbfrom="pubmed",
                db="pubmed",
                linkname="pubmed_pubmed_refs",
                id=pmid
            )
            record_refs = Entrez.read(handle_refs)
            handle_refs.close()

            if record_refs and record_refs[0]["LinkSetDb"]:
                results[pmid]["References"] = [
                    link["Id"]
                    for link in record_refs[0]["LinkSetDb"][0]["Link"]
                ]

        except Exception as error:
            print(f"Reference fetch error for PMID {pmid}: {error}")

        try:
            handle_cit = Entrez.elink(
                dbfrom="pubmed",
                db="pubmed",
                linkname="pubmed_pubmed_citedin",
                id=pmid
            )
            record_cit = Entrez.read(handle_cit)
            handle_cit.close()

            if record_cit and record_cit[0]["LinkSetDb"]:
                results[pmid]["Citations"] = [
                    link["Id"]
                    for link in record_cit[0]["LinkSetDb"][0]["Link"]
                ]

        except Exception as error:
            print(f"Citation fetch error for PMID {pmid}: {error}")

        time.sleep(0.3)

    return results


def search_and_extract(query, processed, max_total=500, batch_size=50):
    """
    Search PubMed, fetch article metadata,
    and expand with references and citations.
    """
    all_data = []

    handle = Entrez.esearch(
        db="pubmed",
        term=query,
        retmax=1
    )

    total = int(Entrez.read(handle)["Count"])
    handle.close()

    if total == 0:
        return []

    for start in range(0, min(total, max_total), batch_size):

        handle = Entrez.esearch(
            db="pubmed",
            term=query,
            retstart=start,
            retmax=batch_size
        )

        record = Entrez.read(handle)
        handle.close()

        ids = record["IdList"]

        if not ids:
            break

        # Keep only new PubMed IDs
        new_ids = [pmid for pmid in ids if pmid not in processed]

        if not new_ids:
            continue

        processed.update(new_ids)

        # Fetch primary articles
        article_text = fetch_articles(new_ids)
        articles = parse_articles(article_text)

        # Keep only articles with abstracts
        articles = [article for article in articles if article.get("Abstract")]

        if not articles:
            continue

        # Fetch references and citations for primary articles
        reference_citation_data = fetch_references_and_citations(
            [article["PMID"] for article in articles]
        )

        # Collect all referenced/citing PMIDs
        related_ids = set()

        for item in reference_citation_data.values():
            related_ids.update(item.get("References", []))
            related_ids.update(item.get("Citations", []))

        # Fetch only related articles not already processed
        new_related_ids = list(related_ids - processed)
        processed.update(new_related_ids)

        related_text = fetch_articles(new_related_ids)
        related_articles = parse_articles(related_text)

        # Keep only related articles with abstracts
        related_articles = [
            article for article in related_articles
            if article.get("Abstract")
        ]

        # Add references and citations to primary articles
        for article in articles:
            pmid = article["PMID"]

            article["References"] = "; ".join(
                reference_citation_data.get(pmid, {}).get("References", [])
            )

            article["Citations"] = "; ".join(
                reference_citation_data.get(pmid, {}).get("Citations", [])
            )

        # Related articles are added without reference expansion
        for article in related_articles:
            article["References"] = ""
            article["Citations"] = ""

        all_data.extend(articles)
        all_data.extend(related_articles)

        time.sleep(0.3)

    return all_data


def save_csv(article_list, output_file):
    """
    Save extracted articles to CSV.
    """
    with open(output_file, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "PMID",
                "Title",
                "Authors",
                "Journal",
                "Date",
                "Abstract",
                "References",
                "Citations"
            ]
        )

        writer.writeheader()
        writer.writerows(article_list)


if __name__ == "__main__":

    queries = read_queries()
    processed_global = set()

    output_dir = Path("data/raw")
    output_dir.mkdir(parents=True, exist_ok=True)

    for query in queries:

        print(f"\n>>> Processing query: {query}")

        processed_local = set(processed_global)

        articles = search_and_extract(
            query,
            processed_local,
            max_total=500
        )

        processed_global.update(processed_local)

        if articles:

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            safe_query = (
                query.replace(" ", "_")
                .replace(":", "")
                .replace("/", "-")
            )

            output_file = output_dir / f"pubmed_{safe_query}_{timestamp}.csv"

            save_csv(articles, output_file)

            print(f"{len(articles)} articles saved to {output_file}")

        else:
            print(f"No valid articles found for query: {query}")