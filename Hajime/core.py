from urllib.parse import parse_qs
import json, uuid, mimetypes, os
from sqlalchemy import create_engine, text, MetaData
from sqlalchemy.orm import sessionmaker


def find_free_port(start_port: int = 8000) -> int:
    import socket
    """Find the next available port starting from start_port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        while True:
            if s.connect_ex(('localhost', start_port)) != 0:
                return start_port
            start_port += 1
class Messages:
    def __init__(self):
        self.green = '\033[92m'
        self.red = '\033[91m'
        self.end = '\033[0m'

    def message(self, status: int = 200, message: object = ""):
        color = self.green if 200 <= status < 300 else self.red if 400 <= status < 500 else self.end
        print(f"[{color} {status} {self.end}] {message}")


def json_response(data, status=200):
    """Return a JSON response"""
    response_body = json.dumps(data)
    headers = [('Content-Type', 'application/json')]

    # Check if the body is already in bytes, if so, don't encode it again.
    if isinstance(response_body, str):
        response_body = response_body.encode()

    return status, headers, response_body

def get_json(environ):
    try:
        length = int(environ.get('CONTENT_LENGTH', 0))
        body = environ['wsgi.input'].read(length)
        return json.loads(body)
    except:
        return None

class Database:
    def __init__(self, db_type, host, user, password, database, port=None):
        self.db_type = db_type.lower()
        self.engine = None
        self.Session = None

        if self.db_type == "postgresql":
            db_url = f"postgresql+psycopg2://{user}:{password}@{host}:{port or 5432}/{database}"
        elif self.db_type == "sqlite":
            db_url = f"sqlite:///{database}"
        else:
            raise ValueError("Unsupported database type. Use 'postgresql' or 'sqlite'.")

        self.engine = create_engine(db_url)
        self.Session = sessionmaker(bind=self.engine)
        self.metadata = MetaData()
        self.metadata.reflect(bind=self.engine)

    def execute_query(self, query, params=None):
        """Executes a query (INSERT, UPDATE, DELETE) and commits the transaction."""
        with self.engine.connect() as connection:
            connection.execute(text(query), params or {})
            connection.commit()

    def fetch_all(self, query, params=None):
        """Executes a SELECT query and returns all results."""
        with self.engine.connect() as connection:
            result = connection.execute(text(query), params or {})
            return result.fetchall()

    def fetch_one(self, query, params=None):
        """Executes a SELECT query and returns a single result."""
        with self.engine.connect() as connection:
            result = connection.execute(text(query), params or {})
            return result.fetchone()

    def get_tables(self):
        """Returns a list of tables in the database."""
        return self.metadata.tables.keys()

    def get_table_data(self, table_name):
        """Fetch all records from a given table."""
        with self.engine.connect() as connection:
            result = connection.execute(text(f"SELECT * FROM {table_name}"))
            return result.fetchall()

    def close(self):
        """Closes the database connection."""
        if self.engine:
            self.engine.dispose()


class Hajime:
    def __init__(self, database = None):
        self.routes = {}
        self.error_handlers = {}
        self.template_folder = "templates"
        self.static_folder = "static"
        self.middlewares = []
        self.sessions = {}
        self.ws_routes = {}
        if database != None:
            self.database = database
    def websocket(self, path):
        """Decorator to register WebSocket routes"""
        def wrapper(func):
            self.ws_routes[path] = func
            return func
        return wrapper

    async def ws_handler(self, websocket, path):
        """Handle WebSocket connections"""
        if path in self.ws_routes:
            await self.ws_routes[path](websocket)
        else:
            await websocket.send("404 Not Found")
            await websocket.close()

    def run_ws_server(self, port=8765):
        import asyncio, websockets
        """Start the WebSocket server inside a new event loop"""
        async def server_task():
            async with websockets.serve(self.ws_handler, "localhost", port):
                await asyncio.Future()  # Keeps the server running

        asyncio.run(server_task())  # Use asyncio.run() to manage the event loop

    def launch(self, port=8000, ws_port=8765):
        """Launch both WSGI and WebSocket servers"""
        from threading import Thread
        from wsgiref.simple_server import make_server

        # Find an available port for HTTP server
        free_port = find_free_port(port)

        # Start WebSocket server in a separate thread
        ws_thread = Thread(target=self.run_ws_server, args=(ws_port,))
        ws_thread.daemon = True
        ws_thread.start()

        server = make_server('localhost', free_port, self)
        print(f"HTTP server running at http://localhost:{free_port}")
        print(f"WebSocket server running at ws://localhost:{ws_port}")
        server.serve_forever()

    def _db_panel_handler(self, params):
        if self.database == None:
            Messages.message(400, "Database not created")
        else:
            tables = self.database.get_tables()
            table_data = {table: self.database.get_table_data(table) for table in tables}

            html = "<h1>Admin Panel</h1>"
            for table, records in table_data.items():
                html += f"<h2>{table}</h2><table border='1'><tr>"
                if records:
                    columns = records[0].keys()
                    html += "".join(f"<th>{col}</th>" for col in columns) + "</tr>"
                    for record in records:
                        html += "<tr>" + "".join(f"<td>{value}</td>" for value in record.values()) + "</tr>"
                html += "</table>"
            return html

    def error_handler(self, status_code):
        def wrapper(func):
            self.error_handlers[status_code] = func
            return func
        return wrapper

    def use(self, middleware_func):
        """Register a middleware function"""
        self.middlewares.append(middleware_func)

    def route(self, path, methods=["GET"]):
        def wrapper(func):
            self.routes[path] = {"func": func, "methods": methods}
            return func

        return wrapper

    def template(self, filename, **context):
        """Loads an HTML file and replaces {{ variables }} with values"""
        # Get the current working directory (project directory)
        project_dir = os.getcwd()

        # Look for templates in the project's template folder
        filepath = os.path.join(project_dir, self.template_folder, filename)

        print(f"Looking for template at: {filepath}")  # Debugging line

        if not os.path.exists(filepath):
            return "Template not found!"

        with open(filepath, "r", encoding="utf-8") as file:
            template = file.read()

        for key, value in context.items():
            template = template.replace(f"{{{{{key}}}}}", str(value))

        return template

    def get_session(self, environ):
        """Fetches or creates a session for the user"""
        cookies = environ.get("HTTP_COOKIE", "")
        session_id = None
        for cookie in cookies.split("; "):
            if cookie.startswith("session_id="):
                session_id = cookie.split("=")[1]

        if not session_id or session_id not in self.sessions:
            session_id = str(uuid.uuid4())
            self.sessions[session_id] = {}

        return session_id, self.sessions[session_id]

    def set_session(self, session_id, data):
        """Updates session data"""
        self.sessions[session_id] = data

    def __call__(self, environ, start_response):
        path = environ['PATH_INFO']
        environ["json"] = get_json(environ)
        query_string = environ.get('QUERY_STRING', "")
        params = parse_qs(query_string)

        if path.startswith("/static/"):
            return self.serve_static(path, start_response)

        # Get or create session
        session_id, session = self.get_session(environ)
        environ["SESSION"] = session

        for middleware in self.middlewares:
            response = middleware(environ, params)
            if response:
                start_response("401 Unauthorized", [('Content-Type', 'text/html')])
                return [response.encode()]

        method = environ['REQUEST_METHOD']
        if path in self.routes:
            route_info = self.routes[path]
            if method in route_info["methods"]:
                response_body = route_info["func"](environ)

                # Handle JSON response properly
                if isinstance(response_body, tuple):  # JSON response case
                    status, headers, body = response_body
                    start_response(f"{status} OK", headers + [('Set-Cookie', f'session_id={session_id}')])

                    # Ensure response_body is bytes
                    return [body] if isinstance(body, bytes) else [body.encode()]

                # Default to HTML response
                start_response("200 OK", [('Content-Type', 'text/html'), ('Set-Cookie', f'session_id={session_id}')])
                return [response_body.encode()]

            else:
                response_body = self.error_handlers.get(405, lambda: "405 Method Not Allowed")()
                start_response("405 Method Not Allowed", [('Content-Type', 'text/html')])
                return [response_body.encode()]
        else:
            response_body = self.error_handlers.get(404, lambda: "404 Not Found")()
            start_response("404 Not Found", [('Content-Type', 'text/html')])
            return [response_body.encode()]

    def auth_middleware(environ, params):
        session = environ.get("SESSION", {})
        if not session.get("user"):
            return "401 Unauthorized", "Unauthorized access"
        return None

    def serve_static(self, path, start_response):
        """Serve static files from the static/ directory"""
        # Get the current working directory (project directory)
        project_dir = os.getcwd()

        # Strip the '/static/' prefix and join with project directory and static folder
        relative_path = path.replace('/static/', '', 1)
        file_path = os.path.join(project_dir, self.static_folder, relative_path)

        print(f"Serving static file: {file_path}")

        if os.path.exists(file_path):
            mime_type, _ = mimetypes.guess_type(file_path)
            with open(file_path, "rb") as f:
                content = f.read()
            start_response("200 OK", [('Content-Type', mime_type or 'application/octet-stream')])
            return [content]
        else:
            start_response("404 Not Found", [('Content-Type', 'text/plain')])
            return [b"404 Not Found"]
