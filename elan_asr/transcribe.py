#!/usr/bin/env python3
"""Offline CPU transcription; ASR suggestions are deliberately left unassigned."""
import argparse
import datetime
import importlib.metadata
import json
import math
import os
from pathlib import Path
import socket
import xml.etree.ElementTree as ET


def deny_network(*args, **kwargs):
    raise RuntimeError("This tool runs offline: network connections are disabled")


def milliseconds(value):
    return int(round(value * 1000))


def srt_time(value):
    ms = milliseconds(value)
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    seconds, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"


def write_outputs(prefix, audio, duration, segments, model_dir):
    document = {
        "duration": duration, "language": "zh", "engine": "faster-whisper",
        "engine_version": importlib.metadata.version("faster-whisper"),
        "model": model_dir.name, "speaker_assignment": "unassigned",
        "timestamp_status": "ASR estimates requiring review against media",
        "segments": segments,
    }
    prefix.with_suffix(".json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    prefix.with_suffix(".srt").write_text("\n".join(
        f"{i}\n{srt_time(s['start'])} --> {srt_time(s['end'])}\n{s['text']}\n"
        for i, s in enumerate(segments, 1)), encoding="utf-8")
    root = ET.Element("ANNOTATION_DOCUMENT", {
        "AUTHOR": "ELAN ASR tools", "DATE": datetime.datetime.now(
            datetime.timezone.utc).isoformat(), "FORMAT": "3.0", "VERSION": "3.0",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:noNamespaceSchemaLocation": "http://www.mpi.nl/tools/elan/EAFv3.0.xsd",
    })
    header = ET.SubElement(root, "HEADER", {"MEDIA_FILE": "", "TIME_UNITS": "milliseconds"})
    import mimetypes
    ET.SubElement(header, "MEDIA_DESCRIPTOR", {
        "MEDIA_URL": audio.as_uri(),
        "MIME_TYPE": mimetypes.guess_type(audio.name)[0] or "application/octet-stream",
        "RELATIVE_MEDIA_URL": os.path.relpath(audio, prefix.parent),
    })
    ET.SubElement(header, "PROPERTY", {"NAME": "ASR_review_status"}).text = (
        "待人工核对文字、时间边界、教师与学生身份及重叠发言")
    times = ET.SubElement(root, "TIME_ORDER")
    tier = ET.SubElement(root, "TIER", {
        "TIER_ID": "ASR_待分人", "LINGUISTIC_TYPE_REF": "asr_segment"})
    for i, s in enumerate(segments, 1):
        for j, field in ((2 * i - 1, "start"), (2 * i, "end")):
            ET.SubElement(times, "TIME_SLOT", {
                "TIME_SLOT_ID": f"ts{j}", "TIME_VALUE": str(milliseconds(s[field]))})
        annotation = ET.SubElement(tier, "ANNOTATION")
        aligned = ET.SubElement(annotation, "ALIGNABLE_ANNOTATION", {
            "ANNOTATION_ID": f"a{i}", "TIME_SLOT_REF1": f"ts{2*i-1}",
            "TIME_SLOT_REF2": f"ts{2*i}"})
        ET.SubElement(aligned, "ANNOTATION_VALUE").text = s["text"]
    ET.SubElement(root, "LINGUISTIC_TYPE", {
        "LINGUISTIC_TYPE_ID": "asr_segment", "TIME_ALIGNABLE": "true",
        "GRAPHIC_REFERENCES": "false"})
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(prefix.with_suffix(".eaf"), encoding="UTF-8", xml_declaration=True)
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Output prefix without extension")
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    audio, model_dir, prefix = args.audio.resolve(), args.model.resolve(), args.output.resolve()
    if not audio.is_file():
        parser.error(f"Missing local media: {audio}")
    if args.threads < 1:
        parser.error("--threads must be positive")
    for filename in ("model.bin", "config.json", "tokenizer.json"):
        if not (model_dir / filename).is_file():
            parser.error(f"Missing offline model file: {filename}")
    if not any((model_dir / name).is_file() for name in ("vocabulary.txt", "vocabulary.json")):
        parser.error("Missing offline model vocabulary (vocabulary.txt or vocabulary.json)")
    if prefix.suffix:
        parser.error("--output must be a prefix without a file extension")
    for ext in (".json", ".srt", ".eaf"):
        if prefix.with_suffix(ext).exists():
            parser.error(f"Refusing to overwrite {prefix.with_suffix(ext)}")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    socket.create_connection = deny_network
    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio
    samples = decode_audio(str(audio), sampling_rate=16000)
    duration = len(samples) / 16000
    if not duration:
        raise ValueError("Media contains no audio samples")
    model = WhisperModel(str(model_dir), device="cpu", compute_type="int8",
                         cpu_threads=args.threads, local_files_only=True)
    iterator, _ = model.transcribe(samples, language="zh", task="transcribe", beam_size=5,
                                  word_timestamps=True, vad_filter=False,
                                  condition_on_previous_text=False)
    # Iterating is essential: faster-whisper defers inference until this point.
    segments = []
    for segment in iterator:
        if not segment.text.strip():
            continue
        start, end = float(segment.start), float(segment.end)
        if not all(math.isfinite(v) for v in (start, end)) or not 0 <= start < end <= duration + 0.25:
            raise ValueError(f"Invalid model timestamp: {start}, {end}, duration={duration}")
        segments.append({"id": len(segments), "start": start, "end": end,
                         "text": segment.text.strip(), "words": [
                             {"start": float(w.start), "end": float(w.end), "word": w.word,
                              "probability": float(w.probability)} for w in segment.words or []]})
    if not segments:
        raise ValueError("No speech recognized; outputs were not created")
    document = write_outputs(prefix, audio, duration, segments, model_dir)
    print(json.dumps({"duration": duration, "segments": len(segments),
                      "text": "".join(s["text"] for s in document["segments"]),
                      "output_prefix": str(prefix)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
