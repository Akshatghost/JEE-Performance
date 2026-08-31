async function api(url,method="GET",body=null){let o={method,headers:{"Content-Type":"application/json"}};if(body)o.body=JSON.stringify(body);let r=await fetch(url,o);if(!r.ok)throw new Error(await r.text());return r.json()}
document.querySelectorAll('.nav a').forEach(a=>{let p=location.pathname.split('/')[1]||'dashboard';if(a.dataset.page===p)a.classList.add('active')});
