function toggleFavorite(event) {
    event.preventDefault();
    if (event.stopPropagation) event.stopPropagation();

    const btn = event.currentTarget;

    if (btn.dataset.login) {
        window.location.href = "{% url 'exercises:login' %}";
        return;
    }

    fetch("{% url 'exercises:toggle_favorite' %}", {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': '{{ csrf_token }}'
        },
        body: JSON.stringify({ exercise_id: btn.dataset.id })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            btn.classList.toggle('active', data.is_favorite);
        }
    });
}
