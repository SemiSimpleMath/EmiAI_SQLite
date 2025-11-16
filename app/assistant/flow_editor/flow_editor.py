import sys
import json
import os
import yaml
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton,
                             QTextEdit, QFileDialog, QLabel, QGraphicsScene, QGraphicsView, QGraphicsEllipseItem,
                             QListWidget, QListWidgetItem)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QPen

AGENTS_DIR = "agents"  # Base directory where agents are stored
TOOLS_DIR = "tools"  # Base directory for tools

class AgentNode(QGraphicsEllipseItem):
    def __init__(self, x, y, name, gui):
        super().__init__(0, 0, 50, 50)
        self.setBrush(QBrush(Qt.blue))
        self.setPen(QPen(Qt.black))
        self.setPos(x, y)
        self.name = name
        self.gui = gui

    def mousePressEvent(self, event):
        self.gui.load_agent_prompts(self.name)

class ManagerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MultiAgentManager GUI")
        self.setGeometry(100, 100, 1000, 600)

        self.config = None
        self.current_agent = None
        self.current_tool = None
        self.current_prompt_file = None

        # Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Load Config Button
        self.load_button = QPushButton("Load Manager Config")
        self.load_button.clicked.connect(self.load_config)
        layout.addWidget(self.load_button)

        # Graphics View for Nodes
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        layout.addWidget(self.view)

        # Agent List
        self.agent_list = QListWidget()
        self.agent_list.itemClicked.connect(self.load_agent_prompts)
        layout.addWidget(self.agent_list)

        # Tool List
        self.tool_list = QListWidget()
        self.tool_list.itemClicked.connect(self.load_tool_subtools)
        layout.addWidget(self.tool_list)

        # Sub-tool List
        self.subtool_list = QListWidget()
        self.subtool_list.itemClicked.connect(self.load_subtool_prompts)
        layout.addWidget(self.subtool_list)

        # Prompt File List
        self.prompt_list = QListWidget()
        self.prompt_list.itemClicked.connect(self.load_prompt_file)
        layout.addWidget(self.prompt_list)

        # Agent Prompt Editor
        self.agent_label = QLabel("Select an Agent or Tool to Edit Prompts")
        layout.addWidget(self.agent_label)
        self.prompt_editor = QTextEdit()
        layout.addWidget(self.prompt_editor)

        # Save Button
        self.save_button = QPushButton("Save Prompt Changes")
        self.save_button.clicked.connect(self.save_prompt_changes)
        self.save_button.setEnabled(False)
        layout.addWidget(self.save_button)

        # Load tools on startup
        self.populate_tool_list()

    def load_config(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Open Manager Config", "", "YAML Files (*.yaml)")
        if file_name:
            with open(file_name, 'r') as f:
                self.config = yaml.safe_load(f)
            self.draw_graph()
            self.populate_agent_list()

    def draw_graph(self):
        self.scene.clear()
        if not self.config or 'agents' not in self.config:
            return

        # Draw Manager Node
        manager_node = AgentNode(350, 50, "Manager", self)
        manager_node.setBrush(QBrush(Qt.red))
        self.scene.addItem(manager_node)

        # Draw Agent Nodes
        y_offset = 150
        for agent in self.config['agents']:
            agent_node = AgentNode(350, y_offset, agent['name'], self)
            self.scene.addItem(agent_node)
            y_offset += 100

    def populate_agent_list(self):
        self.agent_list.clear()
        if not self.config or 'agents' not in self.config:
            return
        for agent in self.config['agents']:
            item = QListWidgetItem(agent['name'])
            self.agent_list.addItem(item)

    def populate_tool_list(self):
        self.tool_list.clear()
        if os.path.exists(TOOLS_DIR):
            for tool in os.listdir(TOOLS_DIR):
                tool_path = os.path.join(TOOLS_DIR, tool)
                if os.path.isdir(tool_path):
                    item = QListWidgetItem(tool)
                    self.tool_list.addItem(item)

    def load_tool_subtools(self, item):
        tool_name = item.text()
        self.current_tool = tool_name
        self.subtool_list.clear()
        tool_dir = os.path.join(TOOLS_DIR, tool_name)
        if os.path.exists(tool_dir):
            for subtool in os.listdir(tool_dir):
                subtool_path = os.path.join(tool_dir, subtool)
                if os.path.isdir(subtool_path):
                    self.subtool_list.addItem(QListWidgetItem(subtool))

    def load_subtool_prompts(self, item):
        subtool_name = item.text()
        subtool_dir = os.path.join(TOOLS_DIR, self.current_tool, subtool_name, "prompts")
        self.prompt_list.clear()
        if os.path.exists(subtool_dir):
            for prompt_file in os.listdir(subtool_dir):
                if prompt_file.endswith(".j2"):
                    self.prompt_list.addItem(QListWidgetItem(os.path.join(subtool_dir, prompt_file)))

    def load_prompt_file(self, item):
        file_path = item.text()
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                content = f.read()
            self.prompt_editor.setText(content)
            self.current_prompt_file = file_path
            self.save_button.setEnabled(True)
        else:
            self.prompt_editor.setText("File not found!")

    def save_prompt_changes(self):
        if self.current_prompt_file:
            with open(self.current_prompt_file, 'w') as f:
                f.write(self.prompt_editor.toPlainText())
            print(f"Saved changes to {self.current_prompt_file}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ManagerGUI()
    window.show()
    sys.exit(app.exec_())
