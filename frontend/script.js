const API_KEY = '<YOUR_APPSYNC_API_KEY>';  // Replace after deployment
const GRAPHQL_ENDPOINT = '<YOUR_APPSYNC_ENDPOINT>';  // Replace after deployment

// Three.js setup
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(400, 400);
document.getElementById('avatar-container').appendChild(renderer.domElement);

const loader = new THREE.GLTFLoader();
let avatar, mixer, clock = new THREE.Clock();
loader.load('assets/avatar.glb', (gltf) => {
    avatar = gltf.scene;
    scene.add(avatar);
    camera.position.z = 5;

    // Check for morph targets
    avatar.traverse((child) => {
        if (child.isMesh && child.morphTargetDictionary) {
            console.log('Morph Targets:', child.morphTargetDictionary);
        }
    });

    // Animation mixer for procedural movements
    mixer = new THREE.AnimationMixer(avatar);
    animate();
});

const light = new THREE.DirectionalLight(0xffffff, 1);
light.position.set(5, 5, 5);
scene.add(light);
scene.add(new THREE.AmbientLight(0x404040));

// Ghibli-inspired procedural animations
let idleTime = 0;
function animate() {
    requestAnimationFrame(animate);
    const delta = clock.getDelta();
    idleTime += delta;

    if (mixer) mixer.update(delta);

    // Subtle head bob (Ghibli-like idle motion)
    avatar.rotation.y = Math.sin(idleTime * 0.5) * 0.05;
    avatar.rotation.x = Math.cos(idleTime * 0.3) * 0.03;

    // Random blink (if morph target exists)
    if (avatar && avatar.children[0]?.morphTargetInfluences && idleTime > 2) {
        const blinkIdx = avatar.children[0].morphTargetDictionary['blink'];
        if (blinkIdx !== undefined) {
            avatar.children[0].morphTargetInfluences[blinkIdx] = Math.random() > 0.98 ? 1 : 0;
            idleTime = Math.random() > 0.98 ? 0 : idleTime; // Reset on blink
        }
    }

    renderer.render(scene, camera);
}

// AppSync setup
const client = new AWSAppSyncClient({
    url: GRAPHQL_ENDPOINT,
    region: 'us-east-1',
    auth: { type: 'API_KEY', apiKey: API_KEY },
    disableOffline: true
});

client.hydrated().then(() => {
    client.subscribe({
        query: gql`
            subscription {
                onResponse {
                    response
                    audioUrl
                    lipSync
                }
            }
        `
    }).subscribe({
        next: ({ data }) => {
            const { audioUrl, lipSync } = data.onResponse;
            const audio = document.getElementById('response-audio');
            audio.src = audioUrl;
            audio.play();

            // Lip sync with morph targets
            const lipSyncData = JSON.parse(lipSync);
            let i = 0;
            const mesh = avatar.children[0]; // Assuming first child is the mesh
            if (!mesh?.morphTargetInfluences) return;

            const openIdx = mesh.morphTargetDictionary['mouthOpen'];
            const closedIdx = mesh.morphTargetDictionary['mouthClosed'];
            const smileIdx = mesh.morphTargetDictionary['smile'];

            const animateMouth = () => {
                if (i >= lipSyncData.length) {
                    mesh.morphTargetInfluences[openIdx] = 0;
                    mesh.morphTargetInfluences[closedIdx] = 1;
                    mesh.morphTargetInfluences[smileIdx] = 0.2; // Slight smile at rest
                    return;
                }

                const frame = lipSyncData[i];
                const open = frame.mouth_open ? 1 : 0;
                const closed = frame.mouth_open ? 0 : 1;

                // Smooth interpolation (Ghibli-like fluidity)
                mesh.morphTargetInfluences[openIdx] = THREE.MathUtils.lerp(
                    mesh.morphTargetInfluences[openIdx] || 0,
                    open,
                    0.1
                );
                mesh.morphTargetInfluences[closedIdx] = THREE.MathUtils.lerp(
                    mesh.morphTargetInfluences[closedIdx] || 1,
                    closed,
                    0.1
                );
                mesh.morphTargetInfluences[smileIdx] = THREE.MathUtils.lerp(
                    mesh.morphTargetInfluences[smileIdx] || 0,
                    frame.mouth_open ? 0.5 : 0.2, // Subtle smile when speaking
                    0.1
                );

                // Slight head tilt for expressiveness
                avatar.rotation.z = Math.sin(i * 0.1) * 0.05;

                setTimeout(animateMouth, frame.time * 1000);
                i++;
            };
            animateMouth();
        }
    });
});

async function sendMessage() {
    const input = document.getElementById('user-input').value;
    if (!input) return;

    await fetch('https://<API_GATEWAY_ID>.execute-api.us-east-1.amazonaws.com/prod', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: input })
    });
    document.getElementById('user-input').value = '';
}
