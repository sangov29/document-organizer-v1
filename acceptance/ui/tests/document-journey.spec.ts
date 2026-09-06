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
  await page.getByPlaceholder('Email').fill(email);
  await page.getByPlaceholder('Password (12+ chars)').fill(password);
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
  await page.getByPlaceholder('Email').fill(email);
  await page.getByPlaceholder('Password', {exact: true}).fill(password);
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
    }],
  };
  const correctedAnalysis = JSON.parse(JSON.stringify(originalAnalysis));
  correctedAnalysis.fields[0] = {...correctedAnalysis.fields[0], value: '75,000', confidence: null, trust_state: 'corrected', corrections: [{id: 'correction-1', prior_value: '15,000', corrected_value: '75,000', user_id: 'ui-user', prior_provenance_id: 'provenance-1', created_at: new Date().toISOString()}]};
  await page.route(/\/api\/v1\/documents\/[^/]+\/analysis$/, async route => route.fulfill({json: originalAnalysis}));
  await page.route(/\/api\/v1\/documents\/[^/]+\/fields\/field-amount\/review$/, async route => route.fulfill({json: correctedAnalysis}));
  await page.getByRole('link', {name: 'ui-proof-copy.png'}).click();
  await expect(page.getByTestId('document-detail')).toContainText(/kept duplicate/i);
  await expect(page.getByText('Duplicate of')).toBeVisible();
  await expect(page.getByTestId('classification')).toContainText('utility_bill');
  await expect(page.getByTestId('field-amount_due')).toContainText('15,000');
  await page.getByLabel('Correct amount_due').fill('75,000');
  await page.getByTestId('field-amount_due').getByRole('button', {name: 'Save correction'}).click();
  await expect(page.getByRole('status')).toContainText('Correction saved.');
  await expect(page.getByTestId('field-amount_due')).toContainText('15,000 → 75,000');
  await page.screenshot({path: '/evidence/ui-document-detail.png', fullPage: true});

  await page.getByRole('link', {name: /Back to documents/}).click();
  const unusualName = '<img src=x onerror=alert(1)> & ui.png';
  await upload(unusualName, Buffer.concat([PNG, Buffer.from(suffix)]));
  await expect(page.getByRole('link', {name: unusualName})).toBeVisible();
  await page.screenshot({path: '/evidence/ui-documents.png', fullPage: true});

  await page.getByRole('button', {name: 'Logout'}).click();
  await expect(page.getByRole('heading', {name: 'Login'})).toBeVisible();
});
