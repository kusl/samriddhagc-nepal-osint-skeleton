from app.services.procurement_entity_classifier import classify_procurement_entity


def test_classify_ministry_entity():
    result = classify_procurement_entity('Ministry of Home Affairs')
    assert result['entity_bucket'] == 'ministry'


def test_classify_security_agency_entity():
    result = classify_procurement_entity('Nepal Police Headquarters')
    assert result['entity_bucket'] == 'security_agency'


def test_classify_local_government_entity():
    result = classify_procurement_entity('Kathmandu Metropolitan City')
    assert result['entity_bucket'] == 'local_government'


def test_classify_department_entity():
    result = classify_procurement_entity('Department of Roads')
    assert result['entity_bucket'] == 'department_or_office'


def test_classify_organization_entity():
    result = classify_procurement_entity('Nepal Electricity Authority')
    assert result['entity_bucket'] == 'organization'
