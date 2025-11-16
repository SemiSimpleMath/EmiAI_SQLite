from app.assistant.kg_core.kg_pipeline import process_text_to_kg
from app.assistant.database.db_handler import UnifiedLog
from app.assistant.rag_pipeline.source_log_handler import SourceLogHandler

import unicodedata

def normalize_ascii(text):
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


class KGProcessor:
    def __init__(self, source_name=None, log_handler=None, max_batches=20):
        self.source_model = UnifiedLog
        self.source_name = source_name
        self.log_handler = log_handler or SourceLogHandler()
        self.max_batches = max_batches

    def run(self, batch_size=10):
        if self.source_name is None:
            grouped_logs = self.log_handler.fetch_all_unprocessed_logs_grouped_by_source(
                self.source_model,
                filter_roles=['assistant', 'user']
            )
            for source, logs in grouped_logs.items():
                print(f"Processing source: {source} with {len(logs)} entries")
                processor = KGProcessor(source_name=source, max_batches=self.max_batches)
                processor._process_logs(batch_size)
        else:
            self._process_logs(batch_size)

    def _process_logs(self, batch_size):
        total_rows = self.log_handler.count_unprocessed_logs(
            self.source_model,
            self.source_name,
            filter_roles=['assistant', 'user']
            #filter_roles=['unknown']
        )
        rows_processed = 0

        while rows_processed < total_rows and rows_processed < self.max_batches * batch_size:
            first_log = self.log_handler.fetch_unprocessed_logs(
                self.source_model,
                self.source_name,
                filter_roles=['assistant', 'user'],
                #filter_roles=['unknown'],
                batch_size=1
            )
            if not first_log:
                break

            batch_date = first_log[0]['timestamp'].date()
            logs = self.log_handler.fetch_unprocessed_logs_by_date(
                self.source_model,
                self.source_name,
                batch_date,
                filter_roles=['assistant', 'user'],
                # filter_roles=['unknown'],
                batch_size=batch_size
            )
            if not logs:
                break

            print("\n" + "+" * 80)
            print(f"+++ Processing {len(logs)} rows for source '{self.source_name}'")
            print(f"+++ Rows processed: {rows_processed} / {total_rows} | Remaining: {total_rows - rows_processed}")
            print("+" * 80)

            log_context_items = []
            for i, log in enumerate(logs):
                msg = log.get("message", "").strip()
                if not msg:
                    continue

                # build context window of 2 prior messages + current
                window_msgs = [
                    f"{logs[j].get('role', '')}: {logs[j].get('message', '').strip()}"
                    for j in range(i - 2, i + 1)
                    if 0 <= j < len(logs)
                ]

                role = log.get("role", "")
                if role == "user":
                    speaker = "Jukka"
                elif role == "assistant":
                    speaker = "Emi (AI assistant)"
                elif role == "unknown":
                    speaker = "Summary of Chat"
                context_str = " ".join(window_msgs)

                log_context_items.append({
                    "message": normalize_ascii(f"{speaker}: {msg}"),
                    "context_window": normalize_ascii(context_str),
                    "timestamp": log.get("timestamp"),
                    "source": log.get("source")
                })


            if not log_context_items:
                self.log_handler.mark_processed(self.source_model, logs)
                rows_processed += len(logs)
                continue

            process_text_to_kg(log_context_items)
            self.log_handler.mark_processed(self.source_model, logs)
            rows_processed += len(logs)

if __name__ == "__main__":
    import app.assistant.tests.test_setup # This is just run for the import
    
    # TEST MODE: Use fixed test string instead of database
    TEST_MODE = False  # Set to False to use database
    
    if TEST_MODE:
        # Your test string here - modify this as needed
        test_string = """
        Jukka has a brother named Jouko.
        """
        
        # Create a simple test context item
        test_context_item = {
            "message": test_string.strip(),
            "context_window": test_string.strip(),
            "timestamp": "2024-01-01T12:00:00Z",
            "source": "test_mode"
        }
        
        print("🧪 TEST MODE: Using fixed test string")
        print("=" * 80)
        print("Test string:")
        print(test_string.strip())
        print("=" * 80)
        
        # Process the test string
        process_text_to_kg([test_context_item])
        print("✅ Test processing complete!")
        
    else:
        # Normal database mode
        processor = KGProcessor()
        processor.run(batch_size=100)