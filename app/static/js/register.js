document.getElementById('register-form').addEventListener('submit', function(event) {
    event.preventDefault();  // Prevent the default form submission
    const form = document.getElementById('register-form');
    const url = form.getAttribute('data-url');
    alert(url)
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
            return response.json();  // If register is successful, handle JSON response
        } else {
            throw new Error('Failed to log in');  // If not successful, throw an error
        }
    })
    .then(data => {
        document.getElementById('response-message').innerText = 'register successful!';
    })
    .catch(error => {
        console.error('Error:', error);
        document.getElementById('response-message').innerText = 'register failed. Please try again.';
    });
});
