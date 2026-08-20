async page => {
  const sleep = (ms) => page.waitForTimeout(ms);
  const fillStreamlit = async (locator, value) => {
    await locator.click();
    await locator.fill('');
    await locator.pressSequentially(value, { delay: 5 });
    await locator.press('Tab');
    await sleep(800);
  };

  await page.goto('http://localhost:8501/');
  await sleep(3000);
  await fillStreamlit(page.getByRole('textbox', { name: 'Add' }), 'Delete target memory item.');
  await page.getByTestId('stBaseButton-primary').filter({ hasText: 'Save' }).click();
  await sleep(3000);

  // Open via the explicit Open button in the selectbox group
  const group = page.getByRole('combobox', { name: 'Select item' }).locator('xpath=ancestor::*[self::div][1]');
  await page.getByRole('button', { name: 'Open' }).first().click();
  await sleep(1000);
  await page.screenshot({ path: 'output/playwright/select-open.png', fullPage: true });

  const dump = await page.evaluate(() => {
    const all = [...document.querySelectorAll('*')].filter(n => {
      const r = n.getAttribute('role');
      const t = (n.innerText || '').trim();
      return r === 'option' || r === 'listbox' || (t && t.includes('delete_target'));
    }).slice(0, 40);
    return all.map(n => ({
      tag: n.tagName,
      role: n.getAttribute('role'),
      text: (n.innerText || '').trim().slice(0, 100),
      testid: n.getAttribute('data-testid'),
    }));
  });

  // Try keyboard approach: focus combobox and ArrowDown
  await page.getByRole('combobox', { name: 'Select item' }).focus();
  await page.keyboard.press('ArrowDown');
  await sleep(800);
  const opts = page.getByRole('option');
  const count = await opts.count();
  let deleted = false;
  if (count > 0) {
    await opts.nth(count > 1 ? 1 : 0).click();
    await sleep(500);
    await page.getByRole('button', { name: 'Delete' }).click();
    await sleep(2500);
    deleted = (await page.locator('body').innerText()).includes('Deleted');
  }

  // Alternative: use st.selectbox by typing into combobox
  if (!deleted) {
    await page.getByRole('combobox', { name: 'Select item' }).click();
    await page.keyboard.type('delete_target');
    await sleep(500);
    await page.keyboard.press('Enter');
    await sleep(800);
    await page.getByRole('button', { name: 'Delete' }).click();
    await sleep(2500);
    deleted = (await page.locator('body').innerText()).includes('Deleted');
  }

  return { optionCount: count, dump, deleted, body: (await page.locator('body').innerText()).slice(0, 600) };
}
