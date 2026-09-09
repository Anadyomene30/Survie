// swift-tools-version: 5.9
import PackageDescription

// SurvieCore ne dépend de rien d'externe : Foundation, SQLite3 et Accelerate
// suffisent. C'est délibéré — le cœur du moteur se compile et se teste sans
// réseau et sans MLX, ce qui permet de vérifier la parité avec l'implémentation
// Python avant de toucher au modèle.
//
// Seule la cible applicative tire MLX. Décommenter ses dépendances après un
// premier `swift build` réussi de SurvieCore.

let package = Package(
    name: "Survie",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "SurvieCore", targets: ["SurvieCore"]),
        .executable(name: "survie-cli", targets: ["SurvieCLI"]),
        .executable(name: "SurvieApp", targets: ["SurvieApp"]),
    ],
    dependencies: [
        // .package(url: "https://github.com/ml-explore/mlx-swift", from: "0.21.0"),
        // .package(url: "https://github.com/ml-explore/mlx-swift-lm", branch: "main"),
    ],
    targets: [
        .target(name: "SurvieCore"),
        .executableTarget(name: "SurvieCLI", dependencies: ["SurvieCore"]),
        // SurvieApp compile SANS MLX : les adaptateurs sont derrière un
        // #if canImport, et l'application reste utilisable en mode extraits
        // seuls, le mode urgence fonctionnant intégralement. Ajouter les
        // dépendances mlx-swift ci-dessus active la génération.
        .executableTarget(
            name: "SurvieApp",
            dependencies: [
                "SurvieCore",
                // .product(name: "MLXEmbedders", package: "mlx-swift-lm"),
                // .product(name: "MLXLLM", package: "mlx-swift-lm"),
            ],
            swiftSettings: [.unsafeFlags(["-parse-as-library"])]
        ),
        .testTarget(name: "SurvieCoreTests", dependencies: ["SurvieCore"]),
    ]
)
