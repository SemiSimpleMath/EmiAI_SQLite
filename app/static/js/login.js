document.getElementById('login-form').addEventListener('submit', function(event) {
    event.preventDefault();  // Prevent the default form submission
    const form = document.getElementById('login-form');
    const url = form.getAttribute('data-url');
    const formData = {
        username: form.querySelector('#username').value,
        password: form.querySelector('#password').value
    };

    fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(formData)
    })
    .then(response => {
        if (response.ok) {
            return response.json();  // If login is successful, handle JSON response
        } else {
            throw new Error('Failed to log in');  // If not successful, throw an error
        }
    })
    .then(data => {
        if (data.access_token) {
            document.getElementById('response-message').innerText = 'Login successful!';
            // Store the access token in local storage
            localStorage.setItem('access_token', data.access_token);
            // Redirect to the next URL
            window.location.href = data.next_url;
        }
    })
    .catch(error => {
        console.error('Error:', error);
        document.getElementById('response-message').innerText = 'Login failed. Please try again.';
    });
});
