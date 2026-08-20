async page => {
  const sleep = (ms) => page.waitForTimeout(ms);
  await page.goto('http://localhost:8501/');
  await sleep(3500);
  const body = await page.locator('body').innerText();
  const noDocs = body.includes('No documents yet.');
  const noMem = body.includes('No memories yet.');
  await page.getByRole('combobox', { name: 'Select item' }).click();
  await sleep(1000);
  // dump candidate option nodes
  const info = await page.evaluate(() => {
    const nodes = [...document.querySelectorAll('[role="option"], [data-baseweb="menu"] li, ul li, [role="listbox"] *')];
    return nodes.slice(0, 30).map(n => ({
      tag: n.tagName,
      role: n.getAttribute('role'),
      text: (n.innerText || '').trim().slice(0, 80),
      cls: n.className?.toString?.().slice(0, 80),
    }));
  });
  // also try clicking the Open button beside combobox
  const openBtn = page.getByRole('combobox', { name: 'Select item' }).locator('xpath=ancestor::div[1]').getByRole('button');
  const openCount = await openBtn.count();
  return { noDocs, noMem, openCount, info, bodySlice: body.slice(0, 800) };
}
