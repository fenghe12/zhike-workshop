from __future__ import annotations

from typing import Any


INTERACTION_ACTS = {
    "ask_for_reasoning",
    "guided_observation",
    "socratic_question",
    "counterfactual_question",
    "retrieval_prompt",
    "attention_check",
    "quiz",
}


def analyze_rehearsal(
    course_structure: dict[str, Any],
    pedagogical_ir: dict[str, Any],
    maximum_interaction_gap_seconds: float = 600.0,
) -> dict[str, Any]:
    pages = list(course_structure.get("pages", []))
    events = list(pedagogical_ir.get("timeline", {}).get("events", []))
    duration = float(pedagogical_ir.get("timeline", {}).get("durationSeconds", 0) or 0)
    issues: list[dict[str, Any]] = []
    page_reports = []
    for page in pages:
        title = str(page.get("title", "")).strip()
        script = str(page.get("script_text", "")).strip()
        points = [str(value) for value in page.get("key_points", [])]
        page_issues = []
        if not title:
            page_issues.append("missing_title")
        if not script:
            page_issues.append("missing_script")
        if len(points) > 6:
            page_issues.append("high_information_density")
        if len(script) > 1000:
            page_issues.append("long_script")
        if len(script) < 25:
            page_issues.append("short_script")
        for issue in page_issues:
            issues.append({"pageId": page.get("page_id"), "type": issue})
        page_reports.append(
            {
                "pageId": page.get("page_id"),
                "title": title,
                "keyPointCount": len(points),
                "scriptLength": len(script),
                "issues": page_issues,
            }
        )

    interaction_times = []
    for event in events:
        act = str(event.get("dialogue", {}).get("act", ""))
        intent = str(event.get("teachingIntent", ""))
        if act in INTERACTION_ACTS or intent == "retrieve_and_self_explain":
            interaction_times.append(float(event.get("start", 0)))
    checkpoints = [0.0, *sorted(interaction_times), duration]
    interaction_gaps = []
    for first, second in zip(checkpoints, checkpoints[1:]):
        gap = second - first
        interaction_gaps.append({"start": first, "end": second, "seconds": round(gap, 3)})
        if gap > maximum_interaction_gap_seconds:
            issues.append(
                {
                    "type": "interaction_gap",
                    "start": first,
                    "end": second,
                    "seconds": round(gap, 3),
                }
            )
    recommended = []
    checkpoint = maximum_interaction_gap_seconds
    while duration > 0 and checkpoint < duration:
        nearest_event = min(
            events,
            key=lambda event: abs(float(event.get("start", 0)) - checkpoint),
            default=None,
        )
        recommended.append(
            {
                "targetTime": checkpoint,
                "nearestEventId": nearest_event.get("eventId") if nearest_event else None,
                "recommendedType": "question_or_visual_change",
            }
        )
        checkpoint += maximum_interaction_gap_seconds
    critical = [issue for issue in issues if issue["type"] in {"missing_script", "interaction_gap"}]
    return {
        "schemaVersion": "2026.1",
        "courseTopic": course_structure.get("course_topic"),
        "pageCount": len(pages),
        "durationSeconds": duration,
        "interactionEventCount": len(interaction_times),
        "maximumInteractionGapSeconds": maximum_interaction_gap_seconds,
        "interactionGaps": interaction_gaps,
        "recommendedCheckpoints": recommended,
        "pageReports": page_reports,
        "issues": issues,
        "criticalIssueCount": len(critical),
        "publishReady": not critical,
    }
