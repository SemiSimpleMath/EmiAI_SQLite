import sys
import psycopg2
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QComboBox, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QPushButton, QVBoxLayout, QHBoxLayout,
    QWidget, QMessageBox, QLabel, QHeaderView, QLineEdit
)
from PyQt5.QtCore import Qt

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PostgreSQL Table & Field Selector")
        self.loading = False  # flag to avoid triggering updates during data load

        # --- PostgreSQL Connection ---
        try:
            # Use your provided connection string.
            self.conn = psycopg2.connect("postgresql://postgres:beckett4721@localhost/emidb")
            self.cursor = self.conn.cursor()
        except Exception as e:
            QMessageBox.critical(self, "Database Connection Error", str(e))
            sys.exit(1)

        # --- Widgets ---
        # Table selection
        self.tableSelector = QComboBox()
        self.tableSelector.currentIndexChanged.connect(self.on_table_change)
        tableLabel = QLabel("Select Table:")

        # Fields selection list
        self.fieldsListWidget = QListWidget()
        fieldsLabel = QLabel("Select Fields to Display:")

        # Button to load the table data based on selected fields
        self.loadTableButton = QPushButton("Load Table")
        self.loadTableButton.clicked.connect(self.load_table_with_fields)

        # Table display widget
        self.tableWidget = QTableWidget()
        self.tableWidget.cellChanged.connect(self.cell_changed)
        self.tableWidget.setSortingEnabled(True)  # Enable sorting

        # Search bar to filter table rows
        searchLabel = QLabel("Search:")
        self.searchBox = QLineEdit()
        self.searchBox.setPlaceholderText("Enter search text...")
        self.searchBox.textChanged.connect(self.search_table)
        searchLayout = QHBoxLayout()
        searchLayout.addWidget(searchLabel)
        searchLayout.addWidget(self.searchBox)

        # Delete and refresh buttons
        self.deleteButton = QPushButton("Delete Selected Row")
        self.deleteButton.clicked.connect(self.delete_row)
        self.refreshButton = QPushButton("Refresh")
        self.refreshButton.clicked.connect(self.refresh_table)

        # --- Layout ---
        topLayout = QHBoxLayout()
        topLayout.addWidget(tableLabel)
        topLayout.addWidget(self.tableSelector)

        fieldsLayout = QVBoxLayout()
        fieldsLayout.addWidget(fieldsLabel)
        fieldsLayout.addWidget(self.fieldsListWidget)
        fieldsLayout.addWidget(self.loadTableButton)

        buttonsLayout = QHBoxLayout()
        buttonsLayout.addWidget(self.refreshButton)
        buttonsLayout.addWidget(self.deleteButton)

        mainLayout = QVBoxLayout()
        mainLayout.addLayout(topLayout)
        mainLayout.addLayout(fieldsLayout)
        mainLayout.addLayout(searchLayout)  # Added search bar layout
        mainLayout.addWidget(self.tableWidget)
        mainLayout.addLayout(buttonsLayout)

        container = QWidget()
        container.setLayout(mainLayout)
        self.setCentralWidget(container)

        # --- Initial Data Load ---
        self.load_table_names()
        if self.tableSelector.count() > 0:
            # Automatically load fields for the first table.
            self.on_table_change()

    def load_table_names(self):
        """Fetch table names from the public schema."""
        try:
            query = """
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema='public'
                ORDER BY table_name;
            """
            self.cursor.execute(query)
            tables = [row[0] for row in self.cursor.fetchall()]
            self.tableSelector.clear()
            self.tableSelector.addItems(tables)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def on_table_change(self):
        """When a new table is selected, load its fields."""
        table_name = self.tableSelector.currentText()
        if table_name:
            self.load_field_names(table_name)

    def load_field_names(self, table_name):
        """Load column names for the selected table and populate the fields list."""
        try:
            query = """
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_schema='public' AND table_name = %s
                ORDER BY ordinal_position;
            """
            self.cursor.execute(query, (table_name,))
            columns = [row[0] for row in self.cursor.fetchall()]
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return

        self.fieldsListWidget.clear()
        self.current_table = table_name
        self.all_fields = columns  # keep track of all columns

        # Assume the first column is the primary key.
        for index, field in enumerate(columns):
            item = QListWidgetItem(field)
            # Force primary key to always be selected and non-editable.
            if index == 0:
                item.setCheckState(Qt.Checked)
                item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
                self.primary_key = field
            else:
                # Uncheck the vector field by default.
                if field.lower() == "vector":
                    item.setCheckState(Qt.Unchecked)
                else:
                    item.setCheckState(Qt.Checked)
            self.fieldsListWidget.addItem(item)

    def load_table_with_fields(self):
        """Build and execute a SELECT query based on selected fields."""
        selected_fields = []
        for i in range(self.fieldsListWidget.count()):
            item = self.fieldsListWidget.item(i)
            if item.checkState() == Qt.Checked:
                selected_fields.append(item.text())
        if not selected_fields:
            QMessageBox.warning(self, "No Fields Selected", "Please select at least one field to display.")
            return

        # Ensure primary key is always in the query.
        if self.primary_key not in selected_fields:
            selected_fields.insert(0, self.primary_key)

        self.load_table_data(selected_fields)

    def load_table_data(self, selected_fields):
        """Load data for the current table showing only the selected fields."""
        self.current_fields = selected_fields
        try:
            fields_sql = ", ".join(selected_fields)
            query = f"SELECT {fields_sql} FROM {self.current_table}"
            self.cursor.execute(query)
            records = self.cursor.fetchall()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return

        self.loading = True
        self.tableWidget.clear()
        self.tableWidget.setRowCount(0)
        self.tableWidget.setColumnCount(len(selected_fields))
        self.tableWidget.setHorizontalHeaderLabels(selected_fields)

        for row_data in records:
            row_index = self.tableWidget.rowCount()
            self.tableWidget.insertRow(row_index)
            for col_index, value in enumerate(row_data):
                item = QTableWidgetItem(str(value))
                # Disable editing on the primary key column.
                if selected_fields[col_index] == self.primary_key:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.tableWidget.setItem(row_index, col_index, item)

        # Adjust columns to fill available space.
        self.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.loading = False

    def search_table(self):
        """Filter rows based on search text."""
        search_text = self.searchBox.text().lower().strip()
        for row in range(self.tableWidget.rowCount()):
            row_matches = False
            for col in range(self.tableWidget.columnCount()):
                item = self.tableWidget.item(row, col)
                if item and search_text in item.text().lower():
                    row_matches = True
                    break
            self.tableWidget.setRowHidden(row, not row_matches)

    def cell_changed(self, row, col):
        """Update the database when a cell is edited."""
        if self.loading:
            return  # ignore changes during table load
        try:
            pk_value = self.tableWidget.item(row, 0).text()  # primary key is in column 0
            new_value = self.tableWidget.item(row, col).text()
            column_name = self.current_fields[col]
            query = f"UPDATE {self.current_table} SET {column_name} = %s WHERE {self.primary_key} = %s"
            self.cursor.execute(query, (new_value, pk_value))
            self.conn.commit()
        except Exception as e:
            QMessageBox.critical(self, "Error Updating Cell", str(e))
            self.conn.rollback()

    def delete_row(self):
        """Safely delete selected visible rows only."""
        selected_items = self.tableWidget.selectedItems()
        if not selected_items:
            return

        selected_rows = {item.row() for item in selected_items if not self.tableWidget.isRowHidden(item.row())}
        pk_values = set()

        for row in selected_rows:
            item = self.tableWidget.item(row, 0)
            if item:
                pk = item.text().strip()
                if pk:
                    pk_values.add(pk)

        if not pk_values:
            QMessageBox.warning(self, "No Valid Primary Keys", "No visible rows with valid primary keys selected.")
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Delete {len(pk_values)} visible row(s)?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            query = f"DELETE FROM {self.current_table} WHERE {self.primary_key} = %s"
            for pk in pk_values:
                self.cursor.execute(query, (pk,))
            self.conn.commit()
            self.refresh_table()
        except Exception as e:
            QMessageBox.critical(self, "Error Deleting Rows", str(e))
            self.conn.rollback()



    def refresh_table(self):
        """Reload the table data using the current selected fields."""
        selected_fields = []
        for i in range(self.fieldsListWidget.count()):
            item = self.fieldsListWidget.item(i)
            if item.checkState() == Qt.Checked:
                selected_fields.append(item.text())
        if self.primary_key not in selected_fields:
            selected_fields.insert(0, self.primary_key)
        self.load_table_data(selected_fields)

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_C:
            self.copy_selected_to_clipboard()
        super().keyPressEvent(event)

    def copy_selected_to_clipboard(self):
        selection = self.tableWidget.selectedRanges()
        if not selection:
            return

        copied_text = ""
        for range_ in selection:
            for row in range(range_.topRow(), range_.bottomRow() + 1):
                row_data = []
                for col in range(range_.leftColumn(), range_.rightColumn() + 1):
                    item = self.tableWidget.item(row, col)
                    row_data.append(item.text() if item else "")
                copied_text += "\t".join(row_data) + "\n"

        clipboard = QApplication.clipboard()
        clipboard.setText(copied_text.strip())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(900, 600)
    window.show()
    sys.exit(app.exec_())
