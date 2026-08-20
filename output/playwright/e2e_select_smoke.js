async page => {
  const sleep = (ms) => page.waitForTimeout(ms);
  const fillStreamlit = async (locator, value) => {
    await locator.click();
    await locator.fill('');
    await locator.pressSequentially(value, { delay: 5 });
    await locator.press('Tab');
    await sleep(600);
  };

  await page.goto('http://localhost:8501/');
  await sleep(3000);
  await fillStreamlit(page.getByRole('textbox', { name: 'Add' }), 'Selectbox smoke memory.');
  await page.getByTestId('stBaseButton-primary').filter({ hasText: 'Save' }).click();
  await sleep(3000);

  const box = page.getByRole('combobox', { name: 'Select item' });
  await box.click();
  await sleep(200);
  await page.keyboard.press('ArrowDown');
  await sleep(800);
  let count = await page.getByRole('option').count();
  if (!count) {
    await page.getByRole('button', { name: 'Open' }).first().click();
    await sleep(500);
    await page.keyboard.press('ArrowDown');
    await sleep(800);
    count = await page.getByRole('option').count();
  }
  let deleted = false;
  if (count > 0) {
    await page.getByRole('option').nth(count > 1 ? 1 : 0).click();
    await sleep(500);
    await page.getByRole('button', { name: 'Delete' }).click();
    await sleep(2500);
    deleted = (await page.locator('body').innerText()).includes('Deleted');
  }
  return { select_options: count > 0, count, deleted };
}
