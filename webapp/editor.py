from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
import os
import requests
import uvicorn
from services.document_service import DocumentService

app = FastAPI()
DOC_SVC = DocumentService()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output/course_works")

@app.get("/edit", response_class=HTMLResponse)
async def edit_page(user_id: int, order_id: int, file: str):
    file_path = os.path.join(OUTPUT_DIR, file)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    text = DOC_SVC.extract_text_from_docx(file_path)
    html = f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Edit document</title>
        <style>textarea{{width:100%;height:70vh;font-family:Arial, sans-serif}}</style>
      </head>
      <body>
        <h3>Edit your document</h3>
        <form method="post" action="/save">
          <input type="hidden" name="user_id" value="{user_id}">
          <input type="hidden" name="order_id" value="{order_id}">
          <input type="hidden" name="file" value="{file}">
          <textarea name="edited_text">{text}</textarea>
          <br/>
          <button type="submit">Save and send to Telegram</button>
        </form>
      </body>
    </html>
    """
    return HTMLResponse(content=html)

@app.post("/save")
async def save_edited(user_id: int = Form(...), order_id: int = Form(...), file: str = Form(...), edited_text: str = Form(...)):
    # create new docx from edited text
    topic = f"Edited_{{order_id}}"
    author_name = ""
    lang = "uz"
    new_path = await DOC_SVC.create_doc_from_edited_text(topic, edited_text, author_name, lang)

    # send to user via Telegram Bot API
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="Bot token not configured")

    send_url = f"https://api.telegram.org/bot{{BOT_TOKEN}}/sendDocument"
    with open(new_path, "rb") as f:
        files = {"document": (os.path.basename(new_path), f)}
        data = {"chat_id": user_id, "caption": "🔁 Edited document (saved)"}
        resp = requests.post(send_url, data=data, files=files)

    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Failed to send document via Telegram: {{resp.text}}")

    return HTMLResponse('<html><body><h3>Saved and sent back to Telegram. You can close this window.</h3></body></html>')

# To run locally: uvicorn webapp.editor:app --host 0.0.0.0 --port 8000
