# Import necessary Burp Suite libraries
from burp import IBurpExtender, IContextMenuFactory, IContextMenuInvocation, ITab, IScanIssue, IExtensionStateListener
from java.awt import Component, Font, Color
from java.io import PrintWriter
from javax.swing import JMenuItem, JScrollPane, JTextArea, JPanel, JButton, JLabel, JFileChooser, JOptionPane
from threading import Thread
import subprocess
import os
import re

# BurpExtender class implements core extension functionalities
class BurpExtender(IBurpExtender, IContextMenuFactory, ITab, IExtensionStateListener):

    def registerExtenderCallbacks(self, callbacks):
        self._callbacks = callbacks
        self._helpers = callbacks.getHelpers()
        self._callbacks.setExtensionName("Nmap Scanner")
        self._stdout = PrintWriter(callbacks.getStdout(), True)
        self._stderr = PrintWriter(callbacks.getStderr(), True)  # Ensure error logging is properly set

        self._textarea = JTextArea()
        self._scroll = JScrollPane(self._textarea)
        self._tablearea = JTextArea()
        self._tablescroll = JScrollPane(self._tablearea)
        self._tablearea.setEditable(False)
        self._tablearea.setFont(Font("Monospaced", Font.PLAIN, 12))

        self._panel = JPanel()
        self._export_button = JButton("Export Nmap .nmap", actionPerformed=self.export_nmap_file)
        self._heading = JLabel("Nmap Port Scanner")
        self._heading.setFont(Font("Arial", Font.BOLD, 16))
        self._heading.setForeground(Color(255, 128, 0))

        self._author = JLabel("Author: @TheDarkSideOps")
        self._author.setFont(Font("Arial", Font.ITALIC, 12))
        self._usage_instructions1 = JLabel("Usage:")
        self._usage_instructions1.setFont(Font("Arial", Font.BOLD, 12))
        self._usage_instructions2 = JLabel("1. Right-click the Domain from Sitemap and select 'Run Nmap Scan' to start scanning. OR")
        self._usage_instructions3 = JLabel("2. Right-click a request and select 'Run Nmap Scan' to start scanning")
        self._nmap_command_label = JLabel("Nmap Command Executed:")
        self._nmap_command_label.setFont(Font("Arial", Font.BOLD, 12))
        self._nmap_command = JLabel("Nmap -A <Domain>")
        self._nmap_command.setFont(Font("Arial", Font.PLAIN, 12))

        self._panel.setLayout(None)
        self._heading.setBounds(10, 30, 500, 30)
        self._author.setBounds(10, 60, 300, 30)
        self._usage_instructions1.setBounds(10, 100, 500, 30)
        self._usage_instructions2.setBounds(10, 130, 780, 30)
        self._usage_instructions3.setBounds(10, 160, 780, 30)
        self._nmap_command_label.setBounds(10, 200, 500, 30)
        self._nmap_command.setBounds(10, 230, 500, 30)
        self._scroll.setBounds(10, 270, 780, 730)
        self._tablescroll.setBounds(800, 270, 1377, 730)
        self._export_button.setBounds(10, 1010, 200, 30)

        self._panel.add(self._heading)
        self._panel.add(self._author)
        self._panel.add(self._usage_instructions1)
        self._panel.add(self._usage_instructions2)
        self._panel.add(self._usage_instructions3)
        self._panel.add(self._nmap_command_label)
        self._panel.add(self._nmap_command)
        self._panel.add(self._scroll)
        self._panel.add(self._tablescroll)
        self._panel.add(self._export_button)

        callbacks.addSuiteTab(self)
        callbacks.registerContextMenuFactory(self)

        # Check if Nmap is installed at this point
        if not self.is_nmap_installed():
            # If Nmap is not found, we throw an error and display it in the Burp Suite tabs
            error_message = "Nmap executable not found. Please install Nmap and ensure it's in your system PATH."

            # Log the error to the Output/Errors tab
            self._stderr.println(error_message)

            # Display the error in the Nmap Port Scanner tab
            self._textarea.setForeground(Color.RED)  # Set error text color to red
            self._textarea.setText(error_message)

            # Popup for user interaction
            JOptionPane.showMessageDialog(None, error_message, "Error", JOptionPane.ERROR_MESSAGE)

            return  # Stop further extension loading if Nmap is not found

        # Register the IExtensionStateListener to handle extension unload
        callbacks.registerExtensionStateListener(self)

        self.results = {}
        self._nmap_thread = None  # Store reference to the Nmap scan thread

    def getTabCaption(self):
        return "Nmap Port Scanner"

    def getUiComponent(self):
        return self._panel

    def createMenuItems(self, invocation):
        self._invocation = invocation
        menu_list = []
        menu_item = JMenuItem("Run Nmap Scan", actionPerformed=self.run_nmap_scan)
        menu_list.append(menu_item)
        return menu_list

    def is_nmap_installed(self):
        """Check if Nmap is installed by running 'nmap -v' and catching any OSError."""
        try:
            # Try running 'nmap -v' to check if Nmap is installed and accessible
            process = subprocess.Popen(['nmap', '-v'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            process.communicate()  # We don't need the output, just check if it runs
            return True
        except OSError:
            return False

    def run_nmap_scan(self, event):
        selected_messages = self._invocation.getSelectedMessages()
        if selected_messages:
            url = selected_messages[0].getUrl()
            hostname = url.getHost()
            self._hostname = hostname
            self._nmap_thread = Thread(target=self.run_nmap, args=(hostname, selected_messages))
            self._nmap_thread.start()

    def run_nmap(self, hostname, selected_messages):
        try:
            self._textarea.setText("Running Nmap scan on: " + hostname + "\n")
            self._tablearea.setText("")  
            nmap_output_file = "{}.nmap".format(hostname)
            nmap_command = ["nmap", "-A", "-oN", nmap_output_file, hostname]

            process = subprocess.Popen(nmap_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            ip_address = ""
            open_ports = []
            services = []
            protocols = []
            states = []
            versions = []

            for line in process.stdout:
                self._textarea.append(line)
                ip_address = self.parse_nmap_output(line, hostname, open_ports, services, protocols, states, versions, ip_address)

            self._nmap_command.setText("Nmap -A {}".format(hostname))
            process.wait()
            self.update_tablearea()
            self._textarea.append("\nNmap scan completed.")
            self.raise_nmap_issue(selected_messages[0], hostname)
        except FileNotFoundError:
            # Error message display if Nmap is not installed or found
            error_message = "Error: Nmap executable not found. Please ensure Nmap is installed and available in the system PATH."
            
            # Displaying the error message in the Nmap Port Scanner tab
            self._textarea.append(error_message)
            self._textarea.setForeground(Color.RED)  # Set error text to red

            # Logging the error message in Burp Suite's error/output tab
            self._stderr.println(error_message)

            # Displaying a popup dialog for the error message
            JOptionPane.showMessageDialog(None, error_message, "Error", JOptionPane.ERROR_MESSAGE)
        except Exception as e:
            error_message = "Error: " + str(e)
            self._textarea.append(error_message)
            self._stderr.println(error_message)  # Log the exception in the error/output tab
            JOptionPane.showMessageDialog(None, "An error occurred: " + str(e), "Error", JOptionPane.ERROR_MESSAGE)

    def parse_nmap_output(self, line, hostname, open_ports, services, protocols, states, versions, ip_address):
        ip_match = re.search(r"Nmap scan report for (.*) \(([\d\.]+)\)", line)
        if ip_match:
            ip_address = ip_match.group(2)

        port_match = re.search(r"(\d+)/(tcp|udp)\s+(\w+)\s+(\S+)\s+(.+)", line)
        if port_match:
            port = port_match.group(1)
            protocol = port_match.group(2)
            state = port_match.group(3)
            service = port_match.group(4)
            version = port_match.group(5)
            if (hostname, ip_address, port) not in self.results:
                self.results[(hostname, ip_address, port)] = {
                    "service": service,
                    "protocol": protocol,
                    "state": state,
                    "version": version
                }
            self.update_tablearea()
        return ip_address

    def update_tablearea(self):
        formatted_results = {}
        for (hostname, ip_address, port), details in self.results.items():
            if (hostname, ip_address) not in formatted_results:
                formatted_results[(hostname, ip_address)] = {"ports": [], "details": []}
            formatted_results[(hostname, ip_address)]["ports"].append(port)
            formatted_results[(hostname, ip_address)]["details"].append(details)

        table_text = "{:<30}\t{:<15}\t{:<10}\t{:<10}\t{:<10}\t{:<10}\t{}\n".format(
            "URL", "IP Address", "Open Ports", "Protocol", "State", "Service", "Version")
        for (hostname, ip_address), data in formatted_results.items():
            for port, detail in zip(data["ports"], data["details"]):
                table_text += "{:<30}\t{:<15}\t{:<10}\t{:<10}\t{:<10}\t{:<10}\t{}\n".format(
                    hostname, ip_address, port, detail["protocol"], detail["state"], detail["service"], detail["version"])

        self._tablearea.setText(table_text)

    def raise_nmap_issue(self, selected_message, hostname):
        service = selected_message.getHttpService()
        url = selected_message.getUrl()

        issue_name = "Nmap Port Scan Results"
        issue_detail = "The following open ports and services were identified during an Nmap scan on {}:\n\n".format(hostname)
        for (hostname, ip_address, port), details in self.results.items():
            issue_detail += (
                "Host: {}\nIP Address: {}\nPort: {}\nProtocol: {}\nState: {}\nService: {}\nVersion: {}\n\n".format(
                    hostname, ip_address, port, details["protocol"], details["state"], details["service"], details["version"]
                )
            )

        issue = CustomScanIssue(
            service,
            url,
            [selected_message],
            issue_name,
            issue_detail,
            "Information"
        )
        self._callbacks.addScanIssue(issue)

    def export_nmap_file(self, event):
        try:
            chooser = JFileChooser()
            chooser.setDialogTitle("Save Nmap .nmap File")
            chooser.setFileSelectionMode(JFileChooser.FILES_ONLY)
            if chooser.showSaveDialog(None) == JFileChooser.APPROVE_OPTION:
                dest_file = chooser.getSelectedFile().getAbsolutePath()
                if not dest_file.lower().endswith(".nmap"):
                    dest_file += ".nmap"
                src_file = "{}.nmap".format(self._hostname)
                if os.path.exists(src_file):
                    os.rename(src_file, dest_file)
                    self._textarea.append("\nNmap output exported to: " + dest_file)
                else:
                    self._textarea.append("\nError: .nmap file not found.")
                    JOptionPane.showMessageDialog(None, ".nmap file not found.", "Error", JOptionPane.ERROR_MESSAGE)
        except Exception as e:
            self._textarea.append("Error: " + str(e))
            self._stderr.println("Error: " + str(e))  # Log exception to error/output tab
            JOptionPane.showMessageDialog(None, "An error occurred: " + str(e), "Error", JOptionPane.ERROR_MESSAGE)

    # Method triggered when the extension is unloaded
    def extensionUnloaded(self):
        # Check if the Nmap thread is running and interrupt it if necessary
        if self._nmap_thread and self._nmap_thread.is_alive():
            self._textarea.append("\nExtension is being unloaded. Stopping Nmap scan...")
            self._nmap_thread.join(0)  # Interrupt the thread to stop the ongoing scan
            self._textarea.append("\nNmap scan stopped due to extension unload.")

# CustomScanIssue class to define a custom scan issue for Burp Suite
class CustomScanIssue(IScanIssue):
    def __init__(self, http_service, url, http_messages, issue_name, issue_detail, severity):
        self._http_service = http_service
        self._url = url
        self._http_messages = http_messages
        self._issue_name = issue_name
        self._issue_detail = issue_detail
        self._severity = severity

    def getUrl(self):
        return self._url

    def getHttpMessages(self):
        return self._http_messages

    def getHttpService(self):
        return self._http_service

    def getIssueName(self):
        return self._issue_name

    def getIssueType(self):
        return 0

    def getSeverity(self):
        return self._severity

    def getConfidence(self):
        return "Certain"

    def getIssueBackground(self):
        return "This issue was automatically generated based on the results of an Nmap scan."

    def getRemediationBackground(self):
        return None

    def getIssueDetail(self):
        return self._issue_detail

    def getRemediationDetail(self):
        return "Investigate the exposed services and consider securing or closing unnecessary ports."
