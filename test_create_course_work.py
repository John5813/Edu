"""
# test_create_course_work.py
# Run: python test_create_course_work.py
import asyncio
from services.document_service import DocumentService

sample_content = {
    "title": "Sample Course Work on Testing Footnotes",
    "chapters": [
        {
            "title": "Introduction to Testing",
            "subsections": [
                {
                    "title": "Motivation",
                    "text": "Bu bo'lim mavzuni tanishtiradi va asosiy savollarni ko'rsatadi [1].",
                    "footnotes": [{"id": 1, "text": "Muallif A., 2020, Testing in Practice."}]
                },
                {
                    "title": "Background",
                    "text": "Literatura tahlili natijalari shunday ko'rsatadiki... [2][3].",
                    "footnotes": [
                        {"id": 2, "text": "Muallif B., 2018, Research Methods."},
                        {"id": 3, "text": "Muallif C., 2019, Advanced Studies."}
                    ]
                }
            ]
        },
        {
            "title": "Chapter Two",
            "subsections": [
                {
                    "title": "Methodology",
                    "text": "Tadqiqot metodlari: eksperimental va analitik yondashuvlar [4].",
                    "footnotes": [{"id": 4, "text": "Muallif D., 2017, Methodology Handbook."}]
                }
            ]
        }
    ],
    "references": [
        "Muallif A. (2020). Testing in Practice.",
        "Muallif B. (2018). Research Methods."
    ],
    "footnotes": []
}

async def run_test():
    svc = DocumentService()
    out_path = await svc.create_course_work(
        topic="Testing Footnotes Example",
        content=sample_content,
        author_name="Test Author",
        language="uz"
    )
    print("Created file:", out_path)

if __name__ == "__main__":
    asyncio.run(run_test())
"""