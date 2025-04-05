Various XSS methods. Hopefully the sanitizer doesn't let any of them through.


<script>
   alert("Hello world!");
</script>

<img src=x onerror=alert('XSS')>

<a href="#" onclick="alert('XSS')">Click me</a>

<svg onload=alert('XSS')></svg>

<a href="javascript:alert('XSS')">Click me</a>

<input type="text" value="<script>alert('XSS')</script>">

<script>eval('\x61\x6c\x65\x72\x74\x28\x27\x58\x53\x53\x27\x29')</script>

<svg><script>alert('XSS')</script></svg>

<iframe src="javascript:alert('XSS')"></iframe>

<math><mtext><script>alert('XSS')</script></mtext></math>

<div style="background:url(javascript:alert('XSS'))">

