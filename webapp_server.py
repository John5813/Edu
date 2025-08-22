"""
Simple web server for Telegram Web App
"""

from aiohttp import web
import aiohttp_cors
import os
import logging
import json

logger = logging.getLogger(__name__)

async def index_handler(request):
    """Serve the main web app HTML"""
    with open('webapp/index.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    return web.Response(text=html_content, content_type='text/html')

async def test_handler(request):
    """Serve test web app HTML"""
    with open('test_webapp.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    return web.Response(text=html_content, content_type='text/html')

async def simple_test_handler(request):
    """Serve simple test HTML"""
    with open('simple_test.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    return web.Response(text=html_content, content_type='text/html')

async def template_handler(request):
    """Serve template images"""
    filename = request.match_info.get('filename')
    file_path = os.path.join('webapp/templates', filename)

    if os.path.exists(file_path):
        with open(file_path, 'rb') as f:
            content = f.read()

        # Determine content type
        if filename.endswith('.jpg') or filename.endswith('.jpeg'):
            content_type = 'image/jpeg'
        elif filename.endswith('.png'):
            content_type = 'image/png'
        else:
            content_type = 'application/octet-stream'

        return web.Response(body=content, content_type=content_type)
    else:
        return web.Response(status=404)

class DocumentService:
    """Service for document operations like presentation creation."""
    def __init__(self):
        self.templates_dir = 'webapp/templates'
        if not os.path.exists(self.templates_dir):
            os.makedirs(self.templates_dir)

    async def create_presentation_from_template(self, template_name: str, data: dict) -> str:
        """
        Creates a presentation from a template with given data.
        For now, it just returns a success message.
        In a real application, this would involve more complex logic
        to generate a document (e.g., PDF, PPTX) based on the template and data.
        """
        logger.info(f"Creating presentation from template: {template_name} with data: {data}")
        # Simulate document creation
        # In a real scenario, you would load a template file (e.g., .docx, .pptx)
        # and populate it with data, then save it.
        # For demonstration, we'll just create a dummy file.
        presentation_filename = f"{template_name}_presentation_{hash(json.dumps(data))}.txt"
        presentation_path = os.path.join(self.templates_dir, presentation_filename)

        with open(presentation_path, 'w', encoding='utf-8') as f:
            f.write(f"Presentation based on template: {template_name}\n")
            f.write("Data:\n")
            for key, value in data.items():
                f.write(f"- {key}: {value}\n")

        logger.info(f"Dummy presentation created at: {presentation_path}")
        return presentation_filename # Return a filename or path

async def create_presentation_handler(request):
    """Handler for creating a web app presentation."""
    try:
        data = await request.json()
        template_name = data.get('template_name')
        presentation_data = data.get('data')

        if not template_name or not presentation_data:
            return web.Response(status=400, text="Missing 'template_name' or 'data' in request body")

        document_service = DocumentService()
        result_filename = await document_service.create_presentation_from_template(template_name, presentation_data)

        return web.Response(status=200, text=f"Presentation '{result_filename}' created successfully.")

    except json.JSONDecodeError:
        return web.Response(status=400, text="Invalid JSON format in request body")
    except Exception as e:
        logger.error(f"Error creating presentation: {e}")
        return web.Response(status=500, text="Internal server error during presentation creation")


async def create_webapp():
    """Create and configure web application"""
    app = web.Application()

    # Configure CORS
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*"
        )
    })

    # Add routes
    app.router.add_get('/webapp/', index_handler)
    app.router.add_get('/webapp/index.html', index_handler)
    app.router.add_get('/webapp/templates/{filename}', template_handler)
    app.router.add_post('/webapp/create-presentation', create_presentation_handler)

    # Setup CORS for all routes
    for route in list(app.router.routes()):
        cors.add(route)

    return app

async def start_webapp_server():
    """Start the web app server"""
    app = await create_webapp()
    return app

def main():
    """Main function to start server"""
    app = web.Application()

    # Configure CORS
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*"
        )
    })

    # Add routes
    app.router.add_get('/webapp/', index_handler)
    app.router.add_get('/webapp/index.html', index_handler)
    app.router.add_get('/webapp/templates/{filename}', template_handler)
    app.router.add_post('/webapp/create-presentation', create_presentation_handler)
    app.router.add_get('/test_webapp.html', test_handler)
    app.router.add_get('/simple_test.html', simple_test_handler)

    # Setup CORS for all routes
    for route in list(app.router.routes()):
        cors.add(route)

    web.run_app(app, host='0.0.0.0', port=8080)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting Web App server on port 5000...")
    main()