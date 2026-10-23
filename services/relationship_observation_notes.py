"""Human statements linked to recomputable geometry, never calculation facts.

This stateless adapter returns a record for the caller to store. It does not
diagnose, persist, infer answers or include statements in calculation inputs.
"""
from pydantic import ValidationError

from services.relationship_observation import VERSION, QUESTIONS, DISPLAY_PLANETS, AXES
from services.mcp_result_facts import CalculationReference, verify_calculation_claims_data


def prepare_note(*, reference, person, statement, author_role, point=None, question_id=None):
    if person not in ('a', 'b') or author_role not in ('client_report', 'practitioner_note'):
        return {'status': 'invalid_input', 'error': 'Unknown person or author role.'}
    if not isinstance(statement, str) or not statement.strip() or len(statement) > 4000:
        return {'status': 'invalid_input', 'error': 'statement must contain 1–4000 characters.'}
    if point is not None and point not in DISPLAY_PLANETS + AXES:
        return {'status': 'invalid_input', 'error': 'Unknown natal point.'}
    if question_id is not None and question_id not in QUESTIONS:
        return {'status': 'invalid_input', 'error': 'Unknown observation question.'}
    try:
        ref = CalculationReference.model_validate(reference)
    except (ValidationError, ValueError, TypeError):
        return {'status': 'invalid_reference', 'error': 'Provide an unchanged calculation_reference.'}
    if ref.tool != 'calculate_relationship_observation':
        return {'status': 'invalid_reference', 'error': 'A relationship observation reference is required.'}
    if not ref.input.get('person_' + person):
        return {'status': 'invalid_input', 'error': 'This person was not calculated in the referenced result.'}
    verified = verify_calculation_claims_data(ref.model_dump(), [dict(
        quote='Observation schema anchor', path='/schema_version', value=VERSION)])
    if verified.get('status') != 'ok' or verified.get('counts', {}).get('supported') != 1:
        return {'status': 'invalid_reference', 'error': 'Recalculate the observation before attaching a note.',
                'reference_status': verified.get('status')}
    path = f'/relationship_profiles/{person}' + (f'/points/{point}' if point is not None else '')
    return dict(status='ok', record=dict(schema_version='relationship-observation-note-v1',
        provenance='HUMAN_REPORTED', author_role=author_role, statement=statement,
        person=person, point=point, question_id=question_id,
        source_anchor=dict(reference=ref.model_dump(), path=path),
        anchor_verification='recomputed_reference_matches', statement_verification='not_verified',
        is_calculation_fact=False), persisted=False,
        boundary='Only the source anchor was checked. The human statement is not verified, scored or inferred; caller owns storage.')
