fetch('/catalogue.json').then(r => r.json()).then(d => { document.querySelector('#data-summary').textContent = d.summary; }).catch(() => {});
