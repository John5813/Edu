"""
Simple web server for Telegram Web App
"""

from aiohttp import web
import aiohttp_cors
import os
import logging

logger = logging.getLogger(__name__)

async def index_handler(request):
    """Serve the main web app HTML"""
    with open('webapp/index.html', 'r', encoding='utf-8') as f:
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

    async def handle_root(request):
        return web.Response(text="Web App Server is running", content_type="text/plain")

    async def handle_webapp(request):
        """Serve the webapp interface"""
        try:
            with open('webapp/index.html', 'r', encoding='utf-8') as f:
                html_content = f.read()
            return web.Response(text=html_content, content_type='text/html')
        except FileNotFoundError:
            return web.Response(text="Web app file not found", status=404)

    # Add routes
    app.router.add_get('/', handle_root)
    app.router.add_get('/webapp/', handle_webapp)
    app.router.add_get('/webapp', handle_webapp)

    # Setup CORS for all routes
    for route in list(app.router.routes()):
        cors.add(route)

    web.run_app(app, host='0.0.0.0', port=5000)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting Web App server on port 5000...")
    main()