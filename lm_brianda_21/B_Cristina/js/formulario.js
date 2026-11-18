const formulario = document.getElementById('formulario');
const mensaje = document.getElementById('formulario_mensaje');
const enviar = formulario.querySelector('button[type="submit"]');

formulario.addEventListener('submit', (event) => {
    event.preventDefault();
    mensaje.textContent = 'Datos validados. Este ejercicio no envía mensajes.';
});

formulario.addEventListener('input', () => {
    mensaje.textContent = '';
});

enviar.disabled = false;
