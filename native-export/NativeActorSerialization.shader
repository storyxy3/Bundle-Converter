// Export-only carrier; the offline linker replaces every material shader pointer with the original native shader.
Shader "Hidden/NativeActorSerialization"
{
    Properties
    {
        _BaseMap ("Base", 2D) = "white" {}
        _ShadeMap ("Shade", 2D) = "white" {}
        _DefMap ("Definition", 2D) = "black" {}
        _RampMap ("Ramp", 2D) = "white" {}
        _RampAddMap ("Additional ramp", 2D) = "black" {}
        _HighlightMap ("Highlight", 2D) = "white" {}
        _LayerMap ("Layer", 2D) = "black" {}
        _ReflectionSphereMap ("Reflection sphere", 2D) = "black" {}
        _AnisotropicMap ("Anisotropy", 2D) = "black" {}
        _BumpMap ("Normal", 2D) = "bump" {}
        _EmissionMap ("Emission", 2D) = "black" {}
    }
    SubShader
    {
        Pass
        {
            ColorMask 0
            ZWrite Off
        }
    }
}
