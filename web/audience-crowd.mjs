import * as THREE from 'three';

const BODY_COLORS = [
  0x5dade2,
  0xaf7ac5,
  0xec7063,
  0x48c9b0,
  0xf4d03f,
  0xeb984e,
  0x85c1e9,
  0xaab7b8,
];
const SKIN_COLORS = [0xffdbbd, 0xedbb99, 0xd79a6b, 0xa86f4c];

function randomGenerator(seed = 0x48414b4f) {
  let value = seed >>> 0;
  return () => {
    value = (Math.imul(value, 1664525) + 1013904223) >>> 0;
    return value / 0x100000000;
  };
}

function matrixAt(position, yaw, scale = [1, 1, 1]) {
  const quaternion = new THREE.Quaternion().setFromAxisAngle(
    new THREE.Vector3(0, 1, 0),
    yaw,
  );
  return new THREE.Matrix4().compose(
    new THREE.Vector3(...position),
    quaternion,
    new THREE.Vector3(...scale),
  );
}

function validCameraPosition(cameraState) {
  const value = cameraState?.positionM;
  return Array.isArray(value) && value.length === 3 && value.every(Number.isFinite)
    ? value
    : null;
}

export function createAudienceCrowd(config, cameraState = null) {
  if (config?.enabled !== true) return null;
  const count = Number(config.count);
  const center = config.center_m;
  const width = Number(config.width_m);
  const depth = Number(config.depth_m);
  const ground = Number(config.ground_height_m);
  if (!Number.isInteger(count) || count <= 0
    || !Array.isArray(center) || center.length !== 2 || center.some((v) => !Number.isFinite(v))
    || ![width, depth, ground].every(Number.isFinite) || width <= 0 || depth <= 0) {
    throw new Error('runtime crowd configuration is invalid');
  }

  const random = randomGenerator();
  const camera = validCameraPosition(cameraState);
  const people = [];
  let attempts = 0;
  while (people.length < count && attempts < count * 20) {
    attempts += 1;
    const east = center[0] + (random() - 0.5) * width;
    const north = center[1] + (random() - 0.5) * depth;
    if (camera && Math.hypot(east - camera[0], north - camera[1]) < 4.0) continue;
    const height = 1.45 + random() * 0.45;
    const x = east;
    const z = -north;
    const yaw = Math.atan2(x, z);
    people.push({ x, z, height, yaw, phone: random() < 0.18 });
  }
  if (people.length === 0) return null;

  const group = new THREE.Group();
  group.name = 'drone-show-audience-crowd';

  if (config.lighting?.enabled === true) {
    const intensity = Number(config.lighting.intensity);
    const lightHeight = Number(config.lighting.height_m);
    if (!Number.isFinite(intensity) || intensity <= 0
      || !Number.isFinite(lightHeight) || lightHeight <= 0) {
      throw new Error('runtime crowd lighting configuration is invalid');
    }
    const colors = [0xffc978, 0x79cfff, 0xffc978, 0x79cfff];
    const corners = [
      [-0.45, -0.45],
      [0.45, -0.45],
      [-0.45, 0.45],
      [0.45, 0.45],
    ];
    corners.forEach(([eastRatio, northRatio], index) => {
      const east = center[0] + eastRatio * width;
      const north = center[1] + northRatio * depth;
      const light = new THREE.PointLight(colors[index], intensity, 38, 2);
      light.position.set(east, ground + lightHeight, -north);
      group.add(light);

      const lamp = new THREE.Mesh(
        new THREE.SphereGeometry(0.11, 8, 6),
        new THREE.MeshBasicMaterial({ color: colors[index], toneMapped: false }),
      );
      lamp.position.copy(light.position);
      group.add(lamp);

      const pool = new THREE.Mesh(
        new THREE.CircleGeometry(5.5, 24),
        new THREE.MeshBasicMaterial({
          color: colors[index],
          transparent: true,
          opacity: 0.07,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
          side: THREE.DoubleSide,
          toneMapped: false,
        }),
      );
      pool.rotation.x = -Math.PI / 2;
      pool.position.set(east, ground + 0.035, -north);
      group.add(pool);
    });
  }

  const body = new THREE.InstancedMesh(
    new THREE.CylinderGeometry(0.20, 0.28, 0.82, 6),
    new THREE.MeshBasicMaterial({ vertexColors: true }),
    people.length,
  );
  const heads = new THREE.InstancedMesh(
    new THREE.SphereGeometry(0.16, 8, 6),
    new THREE.MeshBasicMaterial({ vertexColors: true }),
    people.length,
  );
  const legs = new THREE.InstancedMesh(
    new THREE.BoxGeometry(0.13, 0.58, 0.15),
    new THREE.MeshBasicMaterial({ color: 0x566573 }),
    people.length * 2,
  );
  const phones = people.filter((person) => person.phone);
  const phoneLights = new THREE.InstancedMesh(
    new THREE.SphereGeometry(0.035, 6, 4),
    new THREE.MeshBasicMaterial({ color: 0xc8e9ff, toneMapped: false }),
    phones.length,
  );

  let legIndex = 0;
  let phoneIndex = 0;
  people.forEach((person, index) => {
    const ratio = person.height / 1.7;
    body.setMatrixAt(index, matrixAt(
      [person.x, ground + 0.94 * ratio, person.z],
      person.yaw,
      [ratio, ratio, ratio],
    ));
    body.setColorAt(index, new THREE.Color(BODY_COLORS[index % BODY_COLORS.length]));
    heads.setMatrixAt(index, matrixAt(
      [person.x, ground + 1.53 * ratio, person.z],
      person.yaw,
      [ratio, ratio, ratio],
    ));
    heads.setColorAt(index, new THREE.Color(SKIN_COLORS[index % SKIN_COLORS.length]));

    for (const side of [-1, 1]) {
      const localX = side * 0.11 * ratio;
      const offsetX = localX * Math.cos(person.yaw);
      const offsetZ = -localX * Math.sin(person.yaw);
      legs.setMatrixAt(legIndex, matrixAt(
        [person.x + offsetX, ground + 0.29 * ratio, person.z + offsetZ],
        person.yaw,
        [ratio, ratio, ratio],
      ));
      legIndex += 1;
    }

    if (person.phone) {
      phoneLights.setMatrixAt(phoneIndex, matrixAt(
        [person.x, ground + 1.70 * ratio, person.z],
        person.yaw,
        [1, 1, 1],
      ));
      phoneIndex += 1;
    }
  });

  for (const mesh of [body, heads, legs, phoneLights]) {
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.frustumCulled = false;
    group.add(mesh);
  }
  return group;
}
