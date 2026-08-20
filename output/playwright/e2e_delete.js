async page => {
  const sleep = (ms) => page.waitForTimeout(ms);
  const fillStreamlit = async (locator, value) => {
    await locator.click();
    await locator.fill('');
    await locator.pressSequentially(value, { delay: 5 });
    await locator.press('Tab');
    await sleep(800);
  };
  const results = [];

  await page.goto('http://localhost:8501/');
  await sleep(3000);

  await fillStreamlit(page.getByRole('textbox', { name: 'Add' }), 'Delete-me memory for Playwright.');
  await page.getByTestId('stBaseButton-primary').filter({ hasText: 'Save' }).click();
  await sleep(3000);
  let body = await page.locator('body').innerText();
  results.push({ step: 'seed', ok: body.includes('Saved') && !body.includes('No memories yet.'), detail: body.includes('Saved') });

  // open select and pick first real option
  await page.getByRole('combobox', { name: 'Select item' }).click();
  await sleep(1000);
  let options = page.getByRole('option');
  let count = await options.count();
  if (!count) {
    // Streamlit 1.62 may use different option markup
    options = page.locator('[data-testid="stSelectboxVirtualDropdown"] li, [data-baseweb="popover"] li, ul li');
    count = await options.count();
  }
  results.push({ step: 'options_before_delete', ok: count > 0, detail: `count=${count}` });

  if (count > 0) {
    // skip empty placeholder if present
    let idx = 0;
    for (let i = 0; i < count; i++) {
      const t = (await options.nth(i).innerText()).trim();
      if (t && t !== '—') { idx = i; break; }
    }
    const label = (await options.nth(idx).innerText()).trim();
    await options.nth(idx).click();
    await sleep(800);
    await page.getByRole('button', { name: 'Delete' }).click();
    await sleep(2500);
    body = await page.locator('body').innerText();
    results.push({ step: 'delete', ok: body.includes('Deleted'), detail: `label=${label} bodyHasDeleted=${body.includes('Deleted')}` });
  }

  // navigate away and back — persistence check
  await fillStreamlit(page.getByRole('textbox', { name: 'Add' }), 'Persist-me memory after nav.');
  await page.getByTestId('stBaseButton-primary').filter({ hasText: 'Save' }).click();
  await sleep(2500);
  await page.getByRole('link', { name: /Chat/ }).click();
  await sleep(2500);
  await page.getByRole('link', { name: /Documents/ }).click();
  await sleep(3500);
  body = await page.locator('body').innerText();
  results.push({ step: 'persist_after_nav', ok: !body.includes('No memories yet.'), detail: body.slice(0, 400) });

  await page.getByRole('combobox', { name: 'Select item' }).click();
  await sleep(1000);
  options = page.getByRole('option');
  count = await options.count();
  if (!count) {
    options = page.locator('[data-testid="stSelectboxVirtualDropdown"] li, [data-baseweb="popover"] li, ul li');
    count = await options.count();
  }
  results.push({ step: 'options_after_nav', ok: count > 0, detail: `count=${count}` });
  if (count > 0) {
    let idx = 0;
    for (let i = 0; i < count; i++) {
      const t = (await options.nth(i).innerText()).trim();
      if (t && t !== '—') { idx = i; break; }
    }
    await options.nth(idx).click();
    await sleep(500);
    await page.getByRole('button', { name: 'Delete' }).click();
    await sleep(2500);
    body = await page.locator('body').innerText();
    results.push({ step: 'delete_after_nav', ok: body.includes('Deleted'), detail: body.includes('Deleted') });
  }

  return { passed: results.filter(r => r.ok).length, failed: results.filter(r => !r.ok).length, results };
}
