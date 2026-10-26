#!/usr/bin/env python3
"""Validate ASR JSON, SRT and ELAN EAF against a short PCM WAV fixture.

Usage: python tests/verify_asr.py OUTPUT_PREFIX AUDIO.wav [--reference TEXT]
Pass an empty --reference only for audio without a known reference transcript.
This checks an ASR aid, not diarization or overlap accuracy.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
import wave
import xml.etree.ElementTree as ET
from pathlib import Path


DEFAULT_REFERENCE = "欢迎大家来体验达摩院推出的语音识别模型"
TRADITIONAL = str.maketrans("歡來體驗達語識別", "欢来体验达语识别")
SRT_TIMES = re.compile(
    r"^(\d{2,}):(\d{2}):(\d{2}),(\d{3}) --> "
    r"(\d{2,}):(\d{2}):(\d{2}),(\d{3})$"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def finite_number(value: object, label: str) -> float:
    require(isinstance(value, (int, float)) and not isinstance(value, bool),
            f"{label}: expected a number")
    number = float(value)
    require(math.isfinite(number), f"{label}: expected a finite number")
    return number


def normalized(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(TRADITIONAL).lower()
    return "".join(char for char in text if char.isalnum())


def edit_distance(expected: str, actual: str) -> int:
    row = list(range(len(actual) + 1))
    for i, expected_char in enumerate(expected, 1):
        next_row = [i]
        for j, actual_char in enumerate(actual, 1):
            next_row.append(min(next_row[-1] + 1, row[j] + 1,
                                row[j - 1] + (expected_char != actual_char)))
        row = next_row
    return row[-1]


def milliseconds(value: float) -> int:
    return round(value * 1000)


def clock_ms(parts: tuple[str, ...]) -> int:
    hours, minutes, seconds, millis = map(int, parts)
    require(minutes < 60 and seconds < 60, "SRT contains an invalid clock value")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def validate_srt(path: Path, segments: list[dict]) -> None:
    content = path.read_text(encoding="utf-8-sig").strip()
    blocks = re.split(r"\n\s*\n", content.replace("\r\n", "\n"))
    require(len(blocks) == len(segments), "SRT cue count differs from JSON segments")
    for index, (block, segment) in enumerate(zip(blocks, segments), 1):
        lines = block.splitlines()
        require(len(lines) >= 3, f"SRT cue {index} is incomplete")
        require(lines[0].strip() == str(index), f"SRT cue {index} has an invalid index")
        match = SRT_TIMES.fullmatch(lines[1].strip())
        require(match is not None, f"SRT cue {index} has invalid timestamps")
        groups = match.groups()
        start, end = clock_ms(groups[:4]), clock_ms(groups[4:])
        require(start == milliseconds(segment["start"]),
                f"SRT cue {index} start differs from JSON")
        require(end == milliseconds(segment["end"]),
                f"SRT cue {index} end differs from JSON")
        require("\n".join(lines[2:]).strip() == segment["text"].strip(),
                f"SRT cue {index} text differs from JSON")


def validate_eaf(path: Path, segments: list[dict]) -> None:
    root = ET.parse(path).getroot()
    require(root.tag == "ANNOTATION_DOCUMENT", "EAF has an invalid document root")
    tiers = root.findall("TIER")
    require(len(tiers) == 1 and tiers[0].get("TIER_ID") == "ASR_待分人",
            "EAF must use a single ASR_待分人 tier; speaker identities are unverified")
    require(not tiers[0].get("PARTICIPANT"),
            "EAF must not assign an unverified participant")
    slots: dict[str, int] = {}
    for slot in root.findall("./TIME_ORDER/TIME_SLOT"):
        slot_id, value = slot.get("TIME_SLOT_ID"), slot.get("TIME_VALUE")
        require(bool(slot_id) and slot_id not in slots, "EAF has missing/duplicate time-slot IDs")
        require(value is not None and value.isdigit(), "EAF has an invalid time-slot value")
        slots[slot_id] = int(value)
    wrappers = tiers[0].findall("ANNOTATION")
    require(len(wrappers) == len(segments), "EAF annotation count differs from JSON")
    seen_annotations: set[str] = set()
    for index, (wrapper, segment) in enumerate(zip(wrappers, segments), 1):
        require(len(wrapper) == 1 and wrapper[0].tag == "ALIGNABLE_ANNOTATION",
                f"EAF annotation {index} must be time aligned")
        annotation = wrapper[0]
        annotation_id = annotation.get("ANNOTATION_ID")
        require(bool(annotation_id) and annotation_id not in seen_annotations,
                "EAF has missing/duplicate annotation IDs")
        seen_annotations.add(annotation_id)
        ref1, ref2 = annotation.get("TIME_SLOT_REF1"), annotation.get("TIME_SLOT_REF2")
        require(ref1 in slots and ref2 in slots, f"EAF annotation {index} has dangling time references")
        require(slots[ref1] == milliseconds(segment["start"]),
                f"EAF annotation {index} start differs from JSON")
        require(slots[ref2] == milliseconds(segment["end"]),
                f"EAF annotation {index} end differs from JSON")
        value = annotation.find("ANNOTATION_VALUE")
        require(value is not None and (value.text or "").strip() == segment["text"].strip(),
                f"EAF annotation {index} text differs from JSON")


def validate(prefix: Path, audio: Path, reference: str) -> dict:
    payload = json.loads(Path(str(prefix) + ".json").read_text(encoding="utf-8"))
    require(isinstance(payload, dict), "JSON output must be an object")
    duration = finite_number(payload.get("duration"), "duration")
    require(duration > 0, "duration must be positive")
    with wave.open(str(audio), "rb") as wav:
        require(wav.getcomptype() == "NONE", "Fixture must be an uncompressed PCM WAV")
        audio_duration = wav.getnframes() / wav.getframerate()
    require(abs(duration - audio_duration) <= 0.1,
            f"JSON duration {duration} differs from WAV duration {audio_duration}")
    require(payload.get("language") == "zh", "Expected language='zh'")
    segments = payload.get("segments")
    require(isinstance(segments, list) and bool(segments), "ASR returned no segments")
    last_segment_end, word_count = 0.0, 0
    ids: set[object] = set()
    for index, segment in enumerate(segments, 1):
        require(isinstance(segment, dict), f"Segment {index} must be an object")
        segment_id = segment.get("id")
        require(isinstance(segment_id, int) and not isinstance(segment_id, bool)
                and segment_id not in ids, f"Segment {index} has invalid/duplicate ID")
        ids.add(segment_id)
        start = finite_number(segment.get("start"), f"Segment {index} start")
        end = finite_number(segment.get("end"), f"Segment {index} end")
        require(0 <= start < end <= duration + 0.25, f"Segment {index} has invalid bounds")
        require(start >= last_segment_end - 0.001, f"Segment {index} is not monotonic")
        require(isinstance(segment.get("text"), str) and bool(segment["text"].strip()),
                f"Segment {index} has empty text")
        words = segment.get("words")
        require(isinstance(words, list) and bool(words), f"Segment {index} has no word timestamps")
        last_word_end = start
        for word_index, word in enumerate(words, 1):
            require(isinstance(word, dict), f"Segment {index} word {word_index} is invalid")
            word_start = finite_number(word.get("start"), "Word start")
            word_end = finite_number(word.get("end"), "Word end")
            require(0 <= word_start < word_end <= duration + 0.25,
                    f"Segment {index} word {word_index} has invalid bounds")
            require(word_start >= last_word_end - 0.001,
                    f"Segment {index} word {word_index} is not monotonic")
            require(word_start >= start - 0.001 and word_end <= end + 0.001,
                    f"Segment {index} word {word_index} extends beyond its segment")
            require(isinstance(word.get("word"), str) and bool(word["word"].strip()),
                    f"Segment {index} word {word_index} has empty text")
            probability = finite_number(word.get("probability"), "Word probability")
            require(0 <= probability <= 1, "Word probability is outside [0, 1]")
            last_word_end = word_end
            word_count += 1
        last_segment_end = end
    transcript = "".join(segment["text"] for segment in segments)
    require(re.search(r"[\u3400-\u9fff]", transcript) is not None, "ASR returned no Chinese text")
    normalized_transcript, normalized_reference = normalized(transcript), normalized(reference)
    cer = None
    if reference:
        require(bool(normalized_reference), "Reference contains no letters or numbers")
        cer = edit_distance(normalized_reference, normalized_transcript) / len(normalized_reference)
        require(cer <= 0.45, f"Chinese fixture CER {cer:.4f} exceeds 0.45")
        if normalized_reference == normalized(DEFAULT_REFERENCE):
            require("语音" in normalized_transcript and "模型" in normalized_transcript,
                    "Chinese fixture transcript lacks expected key terms 语音/模型")
    validate_srt(Path(str(prefix) + ".srt"), segments)
    validate_eaf(Path(str(prefix) + ".eaf"), segments)
    return {
        "status": "passed",
        "audio_duration_seconds": audio_duration,
        "reported_duration_seconds": duration,
        "language": payload["language"],
        "transcript": transcript,
        "reference": reference or None,
        "normalized_reference": normalized_reference or None,
        "normalized_transcript": normalized_transcript,
        "character_error_rate": cer,
        "maximum_character_error_rate": 0.45 if reference else None,
        "segment_count": len(segments),
        "word_count": word_count,
        "checks": ["Chinese output", "WAV duration", "finite ordered timestamps",
                   "SRT text and millisecond timestamps", "EAF annotation references and timestamps",
                   "unassigned speaker tier"],
        "limitations": [
            "A short single-speaker fixture does not establish classroom transcription accuracy.",
            "Speaker identity and overlapping speech were not tested or assigned.",
            "Timestamp bounds and export consistency do not establish acoustic alignment accuracy.",
            "Reference normalization uses a limited traditional-to-simplified character mapping.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_prefix", type=Path)
    parser.add_argument("audio", type=Path)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    args = parser.parse_args()
    report_path = Path(str(args.output_prefix) + ".validation.json")
    try:
        report = validate(args.output_prefix, args.audio, args.reference)
    except (OSError, ValueError, TypeError, KeyError, ET.ParseError, wave.Error) as error:
        report = {"status": "failed", "error": str(error)}
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
        return 1
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
