const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{const b=await chromium.launch({headless:true,...(process.env.CHROME_PATH ? {executablePath:process.env.CHROME_PATH} : {})});const p=await b.newPage();
await p.addInitScript(()=>{navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException('Permission denied','NotAllowedError')}});
await p.goto(process.env.CLINICVOICE_TEST_URL || 'http://127.0.0.1:5051');await p.getByRole('button',{name:'Start recording',exact:true}).click();await p.getByText(/Microphone unavailable/).waitFor();console.log('PASS microphone denial feedback');
await p.route('**/api/agent-query',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'The assistant is temporarily unavailable. Please try again.'})}));
await p.getByRole('textbox').fill('Hello');await p.getByRole('button',{name:'Send question',exact:true}).click();await p.locator('.error-banner').waitFor();await p.waitForTimeout(500);const message=await p.locator('.error-banner').textContent(); if(message !== 'The assistant is temporarily unavailable. Please try again.') throw new Error(message); console.log('PASS actionable server failure feedback');
await b.close()})().catch(e=>{console.error(e);process.exit(1)});
