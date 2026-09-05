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
  await expect(page.getByRole('heading', {name: 'Documents'})).toBeVisible();

  const upload = async (name: string, body: Buffer) => {
    await page.getByLabel('Choose PDF, JPG or PNG').setInputFiles({name, mimeType: 'image/png', buffer: body});
    await page.getByRole('button', {name: 'Upload', exact: true}).click();
  };
  await upload('ui-proof.png', PNG);
  await expect(page.getByRole('status')).toContainText('Queued ui-proof.png');

  await upload('ui-proof-copy.png', PNG);
  await expect(page.getByRole('alert')).toContainText('Duplicate detected');
  await page.getByRole('button', {name: 'Keep another copy'}).click();
  await expect(page.getByRole('status')).toContainText('Kept duplicate ui-proof-copy.png');
  await expect(page.getByTestId('document-card')).toHaveCount(2);

  await page.getByRole('link', {name: 'ui-proof-copy.png'}).click();
  await expect(page.getByTestId('document-detail')).toContainText(/kept duplicate/i);
  await expect(page.getByText('Duplicate of')).toBeVisible();
  await page.screenshot({path: '/evidence/ui-document-detail.png', fullPage: true});

  await page.getByRole('link', {name: /Back to documents/}).click();
  const unusualName = '<img src=x onerror=alert(1)> & ui.png';
  await upload(unusualName, Buffer.concat([PNG, Buffer.from(suffix)]));
  await expect(page.getByRole('link', {name: unusualName})).toBeVisible();
  await page.screenshot({path: '/evidence/ui-documents.png', fullPage: true});

  await page.getByRole('button', {name: 'Logout'}).click();
  await expect(page.getByRole('heading', {name: 'Login'})).toBeVisible();
});
