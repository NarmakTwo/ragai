async page => {
  const results = [];
  const sleep = (ms) => page.waitForTimeout(ms);
  const shot = async (name) => {
    await page.screenshot({ path: `output/playwright/${name}.png`, fullPage: true });
  };
  const bodyText = async () => page.locator('[data-testid="stAppViewContainer"], [data-testid="stMain"], body').first().innerText();
  const has = async (s) => (await bodyText()).includes(s);
  const noError = async () => {
    const t = await bodyText();
    if (t.includes('StreamlitAPIException') || t.includes('Traceback:')) {
      throw new Error('Streamlit exception: ' + t.slice(0, 600));
    }
  };
  const fillStreamlit = async (locator, value) => {
    await locator.click();
    await locator.fill('');
    await locator.pressSequentially(value, { delay: 5 });
    await locator.press('Tab');
    await sleep(800);
  };
  const clickSave = async () => {
    await page.getByTestId('stBaseButton-primary').filter({ hasText: 'Save' }).click();
    await sleep(3000);
    await noError();
  };

  await page.goto('http://localhost:8501/');
  await sleep(3000);
  await noError();

  // --- short memory ---
  await fillStreamlit(page.getByRole('textbox', { name: 'Add' }), 'Playwright short memory: espresso mornings.');
  await clickSave();
  let statusOk = await has('Saved');
  let listed = !(await has('No memories yet.'));
  results.push({ step: 'save_short_memory', ok: statusOk && listed, detail: `status=${statusOk} listed=${listed} body=${(await bodyText()).slice(0, 300)}` });
  await shot('02-memory');

  // --- long document ---
  const longBody = 'LONGDOC ' + 'x'.repeat(210) + ' Playwright long document.';
  await fillStreamlit(page.getByRole('textbox', { name: 'Add' }), longBody);
  await clickSave();
  statusOk = await has('Saved');
  listed = !(await has('No documents yet.'));
  results.push({ step: 'save_long_document', ok: statusOk && listed, detail: `status=${statusOk} listed=${listed}` });
  await shot('03-document');

  const expanders = page.locator('[data-testid="stExpander"]');
  results.push({ step: 'expanders_present', ok: (await expanders.count()) > 0, detail: `count=${await expanders.count()}` });
  if (await expanders.count()) {
    await expanders.first().click();
    await sleep(500);
  }

  // --- search ---
  await fillStreamlit(page.getByRole('textbox', { name: 'Search' }), 'espresso');
  await sleep(1500);
  results.push({ step: 'search_filter', ok: !(await has('No memories yet.')) || await has('espresso'), detail: `noEmptyMem=${!(await has('No memories yet.'))}` });
  await fillStreamlit(page.getByRole('textbox', { name: 'Search' }), '');
  await sleep(1000);

  // --- file upload ---
  await page.locator('input[type="file"]').first().setInputFiles('output/playwright/sample_upload.txt');
  await sleep(2000);
  await clickSave();
  const uploadOk = await has('Saved') && (await has('sample_upload') || await has('Playwright upload'));
  results.push({ step: 'file_upload_save', ok: uploadOk, detail: `saved=${await has('Saved')} sample=${await has('sample_upload')}` });
  await shot('04-upload');

  // --- select item (Streamlit: focus + ArrowDown opens options) ---
  const openSelect = async (name) => {
    const box = page.getByRole('combobox', { name });
    await box.focus();
    await page.keyboard.press('ArrowDown');
    await sleep(700);
    return page.getByRole('option');
  };
  let options = await openSelect('Select item');
  let optCount = await options.count();
  results.push({ step: 'select_options', ok: optCount > 0, detail: `options=${optCount}` });
  if (optCount > 0) {
    await options.nth(Math.min(1, optCount - 1)).click();
    await sleep(1000);
  }

  await page.getByRole('button', { name: 'Open in editor' }).click();
  await sleep(3000);
  await noError();
  results.push({ step: 'open_editor_nav', ok: page.url().includes('editor'), detail: page.url() });
  await shot('05-editor');

  const idBox = page.getByRole('textbox', { name: 'Id' });
  const textBox = page.getByRole('textbox', { name: 'Text' });

  // If empty editor, create from editor first
  if (!(await idBox.inputValue())) {
    await fillStreamlit(idBox, 'playwright_seed');
    await fillStreamlit(textBox, 'Seed document from editor. '.repeat(10));
    await clickSave();
  }

  const before = await textBox.inputValue();
  await fillStreamlit(textBox, before + '\n\nEdited by Playwright.');
  await clickSave();
  results.push({ step: 'editor_save', ok: await has('Saved') || await has('Created'), detail: await idBox.inputValue() });

  await page.getByRole('button', { name: 'New' }).click();
  await sleep(1500);
  results.push({ step: 'editor_new', ok: (await idBox.inputValue()) === '' || await has('New document'), detail: `id='${await idBox.inputValue()}'` });

  await fillStreamlit(idBox, 'playwright_new_doc');
  await fillStreamlit(textBox, 'Brand new document from Playwright editor test. '.repeat(8));
  await clickSave();
  results.push({ step: 'editor_create', ok: await has('Created') || await has('Saved') || await has('playwright_new_doc'), detail: await idBox.inputValue() });

  await fillStreamlit(textBox, 'temporary dirty text that should be discarded');
  await page.getByRole('button', { name: 'Reload' }).click();
  await sleep(2500);
  await noError();
  const reloaded = await textBox.inputValue();
  results.push({ step: 'editor_reload', ok: !reloaded.includes('temporary dirty text'), detail: reloaded.slice(0, 100) });
  await shot('06-editor-reload');

  // --- chat ---
  await page.getByRole('link', { name: /Chat/ }).click();
  await sleep(3000);
  await noError();
  results.push({ step: 'chat_nav', ok: page.url().includes('chat'), detail: page.url() });

  // expand sidebar
  const collapse = page.locator('[data-testid="stSidebarCollapsedControl"] button, [kind="headerNoPadding"]');
  if (await page.locator('[data-testid="stSidebarCollapsedControl"]').count()) {
    await page.locator('[data-testid="stSidebarCollapsedControl"]').click();
    await sleep(1000);
  }
  results.push({ step: 'chat_settings_visible', ok: await has('Provider') || await has('Temperature') || await has('Settings'), detail: `provider=${await has('Provider')}` });

  const pill = page.getByText('What do you already know about me?');
  if (await pill.count()) {
    await pill.first().click();
    await sleep(12000);
    await noError();
    results.push({ step: 'chat_suggestion', ok: (await page.locator('[data-testid="stChatMessage"]').count()) >= 2, detail: `msgs=${await page.locator('[data-testid="stChatMessage"]').count()}` });
  } else {
    results.push({ step: 'chat_suggestion', ok: false, detail: 'missing pills' });
  }
  await shot('07-chat-suggestion');

  const chatInput = page.locator('[data-testid="stChatInput"] textarea, [data-testid="stChatInputTextArea"], textarea').last();
  await chatInput.click();
  await chatInput.fill('Remember that my favourite food is sushi for Playwright.');
  await chatInput.press('Enter');
  await sleep(15000);
  await noError();
  results.push({ step: 'chat_message', ok: (await page.locator('[data-testid="stChatMessage"]').count()) >= 2, detail: `msgs=${await page.locator('[data-testid="stChatMessage"]').count()}` });
  await shot('08-chat-message');

  await page.getByRole('button', { name: 'Clear chat' }).click();
  await sleep(2000);
  results.push({ step: 'chat_clear', ok: (await page.locator('[data-testid="stChatMessage"]').count()) === 0, detail: `msgs=${await page.locator('[data-testid="stChatMessage"]').count()}` });

  // --- delete ---
  await page.getByRole('link', { name: /Documents/ }).click();
  await sleep(3000);
  await noError();
  options = await openSelect('Select item');
  optCount = await options.count();
  if (optCount > 0) {
    const idx = optCount > 1 ? 1 : 0;
    const label = (await options.nth(idx).innerText()).trim();
    await options.nth(idx).click();
    await sleep(800);
    await page.getByRole('button', { name: 'Delete' }).click();
    await sleep(2500);
    await noError();
    results.push({ step: 'delete_item', ok: await has('Deleted'), detail: `label=${label}` });
  } else {
    results.push({ step: 'delete_item', ok: false, detail: 'no options' });
  }
  await shot('09-delete');

  await page.getByRole('button', { name: 'Transcribe' }).click();
  await sleep(1500);
  results.push({ step: 'transcribe_empty', ok: await has('Record or upload audio first'), detail: 'empty audio warning' });
  await shot('10-final');

  const failed = results.filter(r => !r.ok);
  return { passed: results.length - failed.length, failed: failed.length, results };
}
