from datetime import datetime
from pathlib import Path

from scripts.pubmed_harvester import (
    read_queries,
    search_and_extract,
    save_csv,
)


def main():
    """
    Run a small extraction test using only the first query.
    """

    queries = read_queries()

    if not queries:
        print("No queries found.")
        return

    test_query = queries[0]

    print(f"Running test query:\n{test_query}\n")

    processed = set()

    # Small test extraction
    articles = search_and_extract(
        test_query,
        processed,
        max_total=20,
        batch_size=10
    )

    if not articles:
        print("No articles returned.")
        return

    output_dir = Path("data/raw")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_file = output_dir / f"test_output_{timestamp}.csv"

    save_csv(articles, output_file)

    print(f"{len(articles)} articles saved to {output_file}")


if __name__ == "__main__":
    main()