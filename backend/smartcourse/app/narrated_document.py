"""Retain source document format while associating the spoken course script."""
import shutil
from pathlib import Path


def prepare_narrated_document(source_directory, destination_directory, structure, code):
    source_directory,destination_directory=Path(source_directory),Path(destination_directory)
    destination_directory.mkdir(parents=True,exist_ok=True)
    if structure.get('input_mode')=='existing_pdf':
        destination=destination_directory/'course.pdf'
        shutil.copy2(source_directory/'translated.pdf',destination)
        return destination
    destination=destination_directory/'course-with-narration.pptx'
    shutil.copy2(source_directory/'translated.pptx',destination)
    from .pptx_notes import write_speaker_notes
    from .pptx_fonts import apply_language_font
    write_speaker_notes(destination,structure['pages'])
    apply_language_font(destination,destination,code)
    return destination
