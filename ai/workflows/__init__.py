"""
workflows/ — Multi-step orchestration pipelines.

Workflows chain agents and tools together to complete complex tasks.
They define the execution order, error handling, and retry logic.

Planned workflows:
    - upload_pipeline.py   — file upload → OCR → parse → DB save
    - analysis_pipeline.py — user query → DB fetch → LLM analysis → response
    - report_pipeline.py   — scheduled spending report generation
"""
