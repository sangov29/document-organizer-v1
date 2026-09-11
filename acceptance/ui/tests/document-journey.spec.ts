import {expect, test} from '@playwright/test';

const MAILPIT = process.env.MAILPIT_URL ?? 'http://mailpit:8025';
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
  'base64',
);

test('registration, verification, login, upload, duplicate keep, detail and logout', async ({page, request}) => {
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const email = `ui-acceptance+${suffix}@example.com`;
  const password = `UI-Acceptance-${suffix}!9x`;

  await page.goto('/register');
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', {name: 'Register'}).click();
  await expect(page.getByRole('status')).toContainText('verification instructions');

  let mailText = '';
  await expect.poll(async () => {
    const response = await request.get(`${MAILPIT}/view/latest.txt`, {
      params: {query: `to:"${email}" subject:"Verify"`},
    });
    if (response.ok()) mailText = await response.text();
    return response.status();
  }, {timeout: 30_000}).toBe(200);
  const token = mailText.match(/\/verify-email\?token=([^\s]+)/)?.[1];
  expect(token).toBeTruthy();

  await page.goto(`/verify-email?token=${encodeURIComponent(token!)}`);
  await expect(page.getByText('Email verified. You can now log in.')).toBeVisible();

  await page.goto('/login');
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password', {exact: true}).fill(password);
  await page.getByRole('button', {name: 'Login'}).click();
  await expect(page.getByRole('heading', {name: 'Documents', exact: true})).toBeVisible();

  const upload = async (name: string, body: Buffer) => {
    await page.getByLabel('Choose PDF, JPG or PNG').setInputFiles({name, mimeType: 'image/png', buffer: body});
    await page.getByRole('button', {name: 'Upload', exact: true}).click();
  };
  await upload('ui-proof.png', PNG);
  await expect(page.getByRole('status')).toContainText('Queued ui-proof.png');

  await upload('ui-proof-copy.png', PNG);
  await expect(page.getByText('Duplicate detected', {exact: true})).toBeVisible();
  await page.getByRole('button', {name: 'Keep another copy'}).click();
  await expect(page.getByRole('status')).toContainText('Kept duplicate ui-proof-copy.png');
  await expect(page.getByTestId('document-card')).toHaveCount(2);

  const originalAnalysis = {
    document_id: 'ui-document',
    classification: {
      family: 'utility_bill', confidence: 0.98, provider: 'rules', model_version: 'schema-v0.1', method: 'keyword_rules',
      configured_threshold: 0.75,
      provenance: {id: 'classification-provenance', source_document_id: 'ui-document', source_page_id: null, visual_region_id: null, provider: 'rules', model_version: 'schema-v0.1', method: 'keyword_rules', confidence: 0.98, processed_at: new Date().toISOString()},
    },
    fields: [{
      id: 'field-amount', field_name: 'amount_due', value: '15,000', confidence: 0.91,
      trust_state: 'extracted', criticality: 'critical', schema_version: 'schema-v0.1', corrections: [],
      provenance: {id: 'provenance-1', source_document_id: 'ui-document', source_page_id: 'page-1', visual_region_id: 'region-1', provider: 'tesseract', model_version: '5', method: 'regex', confidence: 0.91, processed_at: new Date().toISOString()},
      sensitive: false, sensitivity_type: null, masked: false,
    }, {
      id: 'field-account', field_name: 'account_number', value: '••••••••1012', confidence: 0.94,
      trust_state: 'extracted', criticality: 'critical', schema_version: 'schema-v0.1', corrections: [],
      provenance: {id: 'provenance-account', source_document_id: 'ui-document', source_page_id: 'page-1', visual_region_id: 'region-account', provider: 'tesseract', model_version: '5', method: 'predefined_field_rules', confidence: 0.94, processed_at: new Date().toISOString()},
      sensitive: true, sensitivity_type: 'financial_account', masked: true,
    }],
    sensitive_regions: [{id: 'region-signature', region_type: 'signature', sensitivity_type: 'signature', bbox: {x: 100, y: 100, width: 220, height: 50}, concealed: true}],
  };
  const correctedAnalysis = JSON.parse(JSON.stringify(originalAnalysis));
  correctedAnalysis.fields[0] = {...correctedAnalysis.fields[0], value: '75,000', confidence: null, trust_state: 'corrected', corrections: [{id: 'correction-1', prior_value: '15,000', corrected_value: '75,000', user_id: 'ui-user', prior_provenance_id: 'provenance-1', created_at: new Date().toISOString()}]};
  await page.route(/\/api\/v1\/documents\/[^/]+\/analysis$/, async route => route.fulfill({json: originalAnalysis}));
  await page.route(/\/api\/v1\/documents\/[^/]+\/fields\/field-amount\/review$/, async route => route.fulfill({json: correctedAnalysis}));
  await page.route(/\/api\/v1\/documents\/[^/]+\/fields\/field-account\/reveal$/, async route => route.fulfill({headers:{'Cache-Control':'no-store'}, json:{subject_type:'extracted_field', subject_id:'field-account', sensitivity_type:'financial_account', revealed_value:'987654321012'}}));
  await page.route(/\/api\/v1\/documents\/[^/]+\/regions\/region-signature\/reveal$/, async route => route.fulfill({headers:{'Cache-Control':'no-store'}, json:{subject_type:'visual_region', subject_id:'region-signature', sensitivity_type:'signature', content_base64:PNG.toString('base64'), media_type:'image/png'}}));
  await page.route(/\/api\/v1\/documents\/[^/]+\/export\.json$/, async route => route.fulfill({headers:{'Content-Type':'application/json'}, body:JSON.stringify({export_schema_version:'export-v0.1', sensitive_export_policy:'masked_no_bulk_reveal_v1'})}));
  await page.getByRole('link', {name: 'ui-proof-copy.png'}).click();
  await expect(page.getByTestId('document-detail')).toContainText(/kept duplicate/i);
  await expect(page.getByText('Canonical document')).toBeVisible();
  await expect(page.getByTestId('classification')).toContainText('Utility Bill');
  await page.getByRole('button', {name:'Download JSON'}).click();
  await expect(page.getByRole('status')).toContainText('JSON export downloaded.');
  await expect(page.getByTestId('field-amount_due')).toContainText('15,000');
  await page.getByLabel('Correct amount_due').fill('75,000');
  await page.getByTestId('field-amount_due').getByRole('button', {name: 'Save correction'}).click();
  await expect(page.getByRole('status')).toContainText('Correction saved.');
  await expect(page.getByTestId('field-amount_due')).toContainText('15,000 → 75,000');
  const accountField = page.getByTestId('field-account_number');
  await expect(accountField).toContainText('••••••••1012 (masked)');
  await accountField.hover();
  await accountField.getByRole('button', {name:'Reveal account number'}).focus();
  await expect(page.getByText('987654321012')).toHaveCount(0);
  await accountField.getByRole('button', {name:'Reveal account number'}).click();
  await expect(accountField).toContainText('987654321012');
  await expect(page.getByTestId('region-signature')).toContainText('Sensitive region concealed');
  await page.reload();
  await expect(page.getByTestId('field-account_number')).toContainText('••••••••1012 (masked)');
  await expect(page.getByText('987654321012')).toHaveCount(0);
  await page.getByTestId('region-signature').getByRole('button', {name:'Reveal signature'}).click();
  await expect(page.getByAltText('Temporarily revealed signature')).toBeVisible();
  await expect(page.getByTestId('field-account_number')).toContainText('••••••••1012 (masked)');
  await page.screenshot({path: '/evidence/ui-document-detail.png', fullPage: true});

  await page.getByRole('link', {name: /Back to documents/}).click();
  await page.route(/\/api\/v1\/documents\/batch\/export\.csv$/, async route => route.fulfill({headers:{'Content-Type':'text/csv'}, body:'document_id,field_name,value\nui-document,amount_due,75000\n'}));
  await page.getByLabel('Select ui-proof-copy.png').check();
  await page.getByRole('button', {name:'Export selected CSV'}).click();
  await expect(page.getByRole('status')).toContainText('Exported 1 document.');
  const unusualName = '<img src=x onerror=alert(1)> & ui.png';
  await upload(unusualName, Buffer.concat([PNG, Buffer.from(suffix)]));
  await expect(page.getByRole('link', {name: unusualName})).toBeVisible();
  await page.screenshot({path: '/evidence/ui-documents.png', fullPage: true});

  await page.getByRole('button', {name: 'Logout'}).click();
  await expect(page.getByRole('heading', {name: 'Login'})).toBeVisible();
});
