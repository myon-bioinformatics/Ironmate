from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import json

# Class for the control message
class ControlMessage:
    def __init__(self, text, number):
        self.text = text
        self.number = number

    def __str__(self):
        return f"Text: {self.text}, Number: {self.number}"

# Request handler class
class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Process GET requests
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(bytes("OK: It's a GET method or URL not in \"/admin\"", "utf-8"))

    def do_POST(self):
        # Process POST requests
        if self.path.startswith("/admin"):
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            params = parse_qs(body)
            text = params.get("text", [None])[0]
            number = params.get("number", [None])[0]

            if text is None or not number.isdigit():
                # Invalid request: missing text or number
                self.send_response(400)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write(bytes("Bad Request", "utf-8"))
                return

            message = ControlMessage(text, int(number))
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(bytes(f"OK, Accepted Control message: {message}", "utf-8"))
            process_message(message)
        else:
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(bytes("OK: It's a GET method or URL not in \"/admin\"", "utf-8"))

# Process the control message
def process_message(message):
    print(f"Accepted Control message: {message}")

# Start the server
def start_server():
    host = "localhost"
    port = 3020
    print(f"Server is started at http://{host}:{port}")

    server = HTTPServer((host, port), RequestHandler)
    server.serve_forever()

if __name__ == "__main__":
    start_server()
